"""
Library System — Views
All redirect() calls use the 'library:' namespace (app_name = 'library').
"""

import datetime
import logging

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction                          # Bug fix #3: removed unused 'models'
from django.db.models import Count, F, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST, require_http_methods

from .models import (
    Account, Author, Book, Borrow,
    Category, Fine, ReadingSession, Reservation,
)

logger = logging.getLogger(__name__)

FINE_RATE_PER_DAY  = 0.50
BORROW_PERIOD_DAYS = 14


# ===========================================================================
# Private helpers
# ===========================================================================

def _apply_overdue_statuses():
    """Bulk-mark BORROWED records past due_date as OVERDUE."""
    Borrow.objects.filter(
        status=Borrow.Status.BORROWED,
        due_date__lt=datetime.date.today(),
    ).update(status=Borrow.Status.OVERDUE)


def _create_fine_if_overdue(borrow, today):
    """
    Create a Fine using get_or_create — safe against duplicate calls.
    Returns (fine | None, created: bool).
    """
    if not borrow.is_overdue:
        return None, False

    overdue_days = (today - borrow.due_date).days
    fine_amount  = round(overdue_days * FINE_RATE_PER_DAY, 2)

    borrow.has_fine = True
    borrow.save(update_fields=["has_fine"])

    fine, created = Fine.objects.get_or_create(
        borrow=borrow,
        defaults={"member": borrow.member, "amount_due": fine_amount},
    )
    return fine, created


def _fulfil_next_reservation(book):
    """Mark the oldest PENDING reservation FULFILLED (FIFO queue)."""
    pending = (
        Reservation.objects
        .filter(book=book, status=Reservation.Status.PENDING)
        .order_by("reserved_on")
        .select_related("member")
        .first()
    )
    if not pending:
        return
    pending.status = Reservation.Status.FULFILLED
    pending.save(update_fields=["status", "updated_at"])
    logger.info("[NOTIFY] reservation_id=%s member=%s book='%s'",
                pending.pk, pending.member.email, book.title)


def _decrement_copies(book, quantity):
    """
    Concurrency-safe decrement via conditional F() UPDATE.
    Returns True if the update succeeded (enough copies available).
    """
    updated = (
        Book.objects
        .filter(pk=book.pk, available_copies__gte=quantity)
        .update(available_copies=F("available_copies") - quantity)
    )
    return updated == 1


# ===========================================================================
# Decorators
# ===========================================================================

def member_required(view_func):
    """Restrict to authenticated members (is_member=True)."""
    @login_required
    def wrapper(request, *args, **kwargs):
        if not request.user.is_member:
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    wrapper.__name__ = view_func.__name__
    return wrapper


def staff_required(view_func):
    """Restrict to staff / librarians (is_staff=True)."""
    @login_required
    def wrapper(request, *args, **kwargs):
        if not request.user.is_staff:
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    wrapper.__name__ = view_func.__name__
    return wrapper


# ===========================================================================
# 1. Auth
# ===========================================================================

@require_http_methods(["GET", "POST"])
def register_view(request):
    if request.user.is_authenticated:
        return redirect("library:dashboard")

    if request.method == "POST":
        first_name = request.POST.get("first_name", "").strip()
        last_name  = request.POST.get("last_name",  "").strip()
        email      = request.POST.get("email",      "").strip().lower()
        username   = request.POST.get("username",   "").strip()
        phone      = request.POST.get("phone",      "").strip()
        gender     = request.POST.get("gender",     "").strip()
        password1  = request.POST.get("password1",  "")
        password2  = request.POST.get("password2",  "")

        errors = []
        if not all([first_name, last_name, email, username, phone, password1]):
            errors.append("All fields are required.")
        if password1 != password2:
            errors.append("Passwords do not match.")
        if len(password1) < 8:
            errors.append("Password must be at least 8 characters.")
        if Account.objects.filter(email=email).exists():
            errors.append("An account with this email already exists.")
        if Account.objects.filter(username=username).exists():
            errors.append("This username is already taken.")

        if errors:
            for error in errors:
                messages.error(request, error)
            return render(request, "auth/register.html", {"form_data": request.POST})

        try:
            user = Account.objects.create_user(
                username=username, email=email, password=password1,
                first_name=first_name, last_name=last_name,
                phone=phone, gender=gender, is_member=True,
            )
            login(request, user)
            messages.success(request, f"Welcome, {user.first_name}! Your account is ready.")
            logger.info("New member registered: %s", email)
            return redirect("library:dashboard")
        except Exception as exc:
            logger.exception("Registration failed for %s: %s", email, exc)
            messages.error(request, "Registration failed. Please try again.")

    return render(request, "auth/register.html")


@require_http_methods(["GET", "POST"])
def login_view(request):
    if request.user.is_authenticated:
        return redirect("library:dashboard")

    if request.method == "POST":
        email    = request.POST.get("email",    "").strip().lower()
        password = request.POST.get("password", "")

        if not email or not password:
            messages.error(request, "Email and password are required.")
            return render(request, "auth/login.html")

        user = authenticate(request, username=email, password=password)

        if user is None:
            messages.error(request, "Invalid email or password.")
            logger.warning("Failed login attempt: %s", email)
            return render(request, "auth/login.html", {"email": email})

        if not user.is_active:
            messages.error(request, "Your account has been disabled. Contact the library.")
            return render(request, "auth/login.html")

        login(request, user)
        logger.info("User logged in: %s", email)

        next_url = request.GET.get("next", "").strip()
        if next_url:
            return redirect(next_url)
        return redirect("library:admin_dashboard" if user.is_staff else "library:dashboard")

    return render(request, "auth/login.html")


@login_required
@require_POST
def logout_view(request):
    logger.info("User logged out: %s", request.user.email)
    logout(request)
    messages.success(request, "You have been logged out successfully.")
    return redirect("library:login")


# ===========================================================================
# 2. Dashboards
# ===========================================================================

@login_required
def dashboard_view(request):
    if request.user.is_staff:
        return redirect("library:admin_dashboard")

    _apply_overdue_statuses()
    user = request.user

    active_borrows = (
        Borrow.objects
        .filter(member=user)
        .exclude(status=Borrow.Status.RETURNED)
        .select_related("book__author")
        .order_by("due_date")
    )
    reservations = (
        Reservation.objects
        .filter(member=user, status=Reservation.Status.PENDING)
        .select_related("book")
    )
    unpaid_fines = (
        Fine.objects
        .filter(member=user)
        .exclude(amount_paid=F("amount_due"))
        .select_related("borrow__book")
    )
    reading_sessions = ReadingSession.objects.filter(member=user).order_by("-date")[:5]
    active_session   = ReadingSession.objects.filter(member=user, time_out__isnull=True).first()

    return render(request, "member/dashboard.html", {
        "active_borrows":   active_borrows,
        "reservations":     reservations,
        "unpaid_fines":     unpaid_fines,
        "reading_sessions": reading_sessions,
        "active_session":   active_session,
        "overdue_count":    active_borrows.filter(status=Borrow.Status.OVERDUE).count(),
    })


@staff_required
def admin_dashboard_view(request):
    _apply_overdue_statuses()
    return render(request, "admin/dashboard.html", {
        "total_books":          Book.objects.count(),
        "total_members":        Account.objects.filter(is_member=True).count(),
        "active_borrows":       Borrow.objects.exclude(status=Borrow.Status.RETURNED).count(),
        "overdue_borrows":      Borrow.objects.filter(status=Borrow.Status.OVERDUE).count(),
        "pending_reservations": Reservation.objects.filter(status=Reservation.Status.PENDING).count(),
        "unpaid_fines":         Fine.objects.filter(amount_paid__lt=F("amount_due")).count(),
        "recent_borrows":       Borrow.objects.select_related("book", "member").order_by("-created_at")[:10],
    })


# ===========================================================================
# 3. Books
# ===========================================================================

def book_list_view(request):
    query       = request.GET.get("q",        "").strip()
    category_id = request.GET.get("category", "").strip()
    books       = Book.objects.select_related("author", "category").order_by("title")

    if query:
        books = books.filter(
            Q(title__icontains=query) |
            Q(author__name__icontains=query) |
            Q(ISBN__icontains=query)
        )
    if category_id:
        books = books.filter(category_id=category_id)

    page = Paginator(books, 12).get_page(request.GET.get("page"))
    return render(request, "books/book_list.html", {
        "page_obj":          page,
        "categories":        Category.objects.all(),
        "query":             query,
        "selected_category": category_id,
    })


def book_detail_view(request, book_id):
    book             = get_object_or_404(Book.objects.select_related("author", "category"), pk=book_id)
    user_borrow      = None
    user_reservation = None

    if request.user.is_authenticated and request.user.is_member:
        user_borrow = (
            Borrow.objects
            .filter(member=request.user, book=book)
            .exclude(status=Borrow.Status.RETURNED)
            .first()
        )
        user_reservation = Reservation.objects.filter(
            member=request.user, book=book, status=Reservation.Status.PENDING
        ).first()

    return render(request, "books/book_detail.html", {
        "book":             book,
        "user_borrow":      user_borrow,
        "user_reservation": user_reservation,
    })


# ===========================================================================
# 4. Authors
# ===========================================================================

def author_list_view(request):
    query   = request.GET.get("q", "").strip()
    authors = Author.objects.all()
    if query:
        authors = authors.filter(name__icontains=query)
    page = Paginator(authors, 20).get_page(request.GET.get("page"))
    return render(request, "books/author_list.html", {"page_obj": page, "query": query})


def author_detail_view(request, author_id):
    author = get_object_or_404(Author, pk=author_id)
    books  = Book.objects.filter(author=author).select_related("category")
    return render(request, "books/author_detail.html", {"author": author, "books": books})


# ===========================================================================
# 5. Categories
# ===========================================================================

def category_list_view(request):
    categories = Category.objects.annotate(book_count=Count("books")).order_by("name")
    return render(request, "books/category_list.html", {"categories": categories})


# ===========================================================================
# 6. Borrow
# ===========================================================================

@member_required
@require_POST
def borrow_book_view(request, book_id):
    book = get_object_or_404(Book, pk=book_id)

    try:
        quantity = max(1, int(request.POST.get("quantity", 1)))
    except (ValueError, TypeError):
        quantity = 1

    if book.available_copies < quantity:
        messages.error(request, f"Only {book.available_copies} copy/copies available.")
        return redirect("library:book_detail", book_id=book_id)

    if Borrow.objects.filter(member=request.user, book=book).exclude(status=Borrow.Status.RETURNED).exists():
        messages.error(request, "You already have an active borrow for this book.")
        return redirect("library:book_detail", book_id=book_id)

    if Fine.objects.filter(member=request.user, amount_paid__lt=F("amount_due")).exists():
        messages.error(request, "You have unpaid fines. Please settle them before borrowing.")
        return redirect("library:dashboard")

    try:
        with transaction.atomic():
            if not _decrement_copies(book, quantity):
                messages.error(request, "Sorry, the last copy was just taken.")
                return redirect("library:book_detail", book_id=book_id)

            borrow = Borrow.objects.create(
                book=book, member=request.user, quantity=quantity,
                start_date=datetime.date.today(),
                due_date=datetime.date.today() + datetime.timedelta(days=BORROW_PERIOD_DAYS),
                status=Borrow.Status.BORROWED,
            )

        messages.success(request, f"You borrowed '{book.title}'. Due back by {borrow.due_date}.")
        logger.info("Borrow created: member=%s book=%s borrow_id=%s",
                    request.user.email, book.title, borrow.pk)
    except Exception as exc:
        logger.exception("Borrow failed: %s", exc)
        messages.error(request, "Something went wrong. Please try again.")

    return redirect("library:dashboard")


@member_required
@require_POST
def return_book_view(request, borrow_id):
    borrow = get_object_or_404(Borrow, pk=borrow_id, member=request.user)

    if borrow.status == Borrow.Status.RETURNED:
        messages.warning(request, "This book has already been returned.")
        return redirect("library:dashboard")

    try:
        with transaction.atomic():
            today              = datetime.date.today()
            borrow.return_date = today
            borrow.status      = Borrow.Status.RETURNED
            borrow.save(update_fields=["return_date", "status"])

            fine, _ = _create_fine_if_overdue(borrow, today)

            if fine:
                overdue_days = (today - borrow.due_date).days
                messages.warning(
                    request,
                    f"'{borrow.book.title}' returned {overdue_days} day(s) late. "
                    f"A fine of ${fine.amount_due} has been applied."
                )
            else:
                messages.success(request, f"'{borrow.book.title}' returned successfully.")

            Book.objects.filter(pk=borrow.book_id).update(
                available_copies=F("available_copies") + borrow.quantity
            )
            _fulfil_next_reservation(borrow.book)

        logger.info("Book returned: member=%s borrow_id=%s", request.user.email, borrow_id)
    except Exception as exc:
        logger.exception("Return failed: borrow_id=%s: %s", borrow_id, exc)
        messages.error(request, "Something went wrong. Please try again.")

    return redirect("library:dashboard")


# ===========================================================================
# 7. Reservation
# ===========================================================================

@member_required
@require_POST
def reserve_book_view(request, book_id):
    book = get_object_or_404(Book, pk=book_id)

    if book.is_available:
        messages.info(request, "This book is available — you can borrow it directly.")
        return redirect("library:book_detail", book_id=book_id)

    if Reservation.objects.filter(member=request.user, book=book, status=Reservation.Status.PENDING).exists():
        messages.warning(request, "You already have a pending reservation for this book.")
        return redirect("library:book_detail", book_id=book_id)

    if Borrow.objects.filter(member=request.user, book=book).exclude(status=Borrow.Status.RETURNED).exists():
        messages.warning(request, "You currently have this book borrowed.")
        return redirect("library:book_detail", book_id=book_id)

    try:
        Reservation.objects.create(book=book, member=request.user)
        messages.success(request, f"You are now in the queue for '{book.title}'.")
        logger.info("Reservation created: member=%s book=%s", request.user.email, book.title)
    except Exception as exc:
        logger.exception("Reservation failed: %s", exc)
        messages.error(request, "Could not create reservation. Please try again.")

    return redirect("library:dashboard")


@member_required
@require_POST
def cancel_reservation_view(request, reservation_id):
    reservation = get_object_or_404(Reservation, pk=reservation_id, member=request.user)

    if reservation.status != Reservation.Status.PENDING:
        messages.warning(request, "This reservation cannot be cancelled.")
        return redirect("library:dashboard")

    reservation.status = Reservation.Status.CANCELLED
    reservation.save(update_fields=["status", "updated_at"])
    messages.success(request, f"Reservation for '{reservation.book.title}' cancelled.")
    logger.info("Reservation cancelled: reservation_id=%s member=%s",
                reservation_id, request.user.email)
    return redirect("library:dashboard")


# ===========================================================================
# 8. Fine
# ===========================================================================

@member_required
@require_POST
def pay_fine_view(request, fine_id):
    fine = get_object_or_404(Fine, pk=fine_id, member=request.user)

    if fine.is_settled:
        messages.info(request, "This fine has already been paid.")
        return redirect("library:dashboard")

    try:
        fine.amount_paid = fine.amount_due
        fine.save(update_fields=["amount_paid"])
        messages.success(request, f"Fine of ${fine.amount_due} paid successfully.")
        logger.info("Fine paid: fine_id=%s member=%s", fine_id, request.user.email)
    except Exception as exc:
        logger.exception("Fine payment failed: fine_id=%s: %s", fine_id, exc)
        messages.error(request, "Payment could not be processed. Please try again.")

    return redirect("library:dashboard")


# ===========================================================================
# 9. Reading Session
# ===========================================================================

@member_required
@require_POST
def reading_check_in_view(request):
    if ReadingSession.objects.filter(member=request.user, time_out__isnull=True).exists():
        messages.warning(request, "You already have an active reading session.")
        return redirect("library:dashboard")

    try:
        ReadingSession.objects.create(member=request.user, time_in=timezone.now())
        messages.success(request, "Reading session started.")
        logger.info("Reading check-in: member=%s", request.user.email)
    except Exception as exc:
        logger.exception("Check-in failed: %s", exc)
        messages.error(request, "Could not start reading session.")

    return redirect("library:dashboard")


@member_required
@require_POST
def reading_check_out_view(request):
    session = ReadingSession.objects.filter(member=request.user, time_out__isnull=True).first()

    if not session:
        messages.warning(request, "No active reading session found.")
        return redirect("library:dashboard")

    try:
        session.time_out = timezone.now()
        session.save(update_fields=["time_out"])
        messages.success(request, f"Reading session ended. Duration: {session.duration_minutes} min.")
        logger.info("Reading check-out: member=%s", request.user.email)
    except Exception as exc:
        logger.exception("Check-out failed: %s", exc)
        messages.error(request, "Could not end reading session.")

    return redirect("library:dashboard")


# ===========================================================================
# 10. Admin — Books
# ===========================================================================

@staff_required
def admin_book_list_view(request):
    _apply_overdue_statuses()
    query = request.GET.get("q", "").strip()
    books = Book.objects.select_related("author", "category")
    if query:
        books = books.filter(Q(title__icontains=query) | Q(ISBN__icontains=query))
    page = Paginator(books, 20).get_page(request.GET.get("page"))
    return render(request, "admin/book_list.html", {"page_obj": page, "query": query})


@staff_required
@require_http_methods(["GET", "POST"])
def admin_book_create_view(request):
    if request.method == "POST":
        try:
            title     = request.POST.get("title",     "").strip()
            ISBN      = request.POST.get("ISBN",      "").strip()
            publisher = request.POST.get("publisher", "").strip()
            summary   = request.POST.get("summary",   "").strip()
            total     = int(request.POST.get("total_copies", 1))
            author    = get_object_or_404(Author,   pk=request.POST.get("author_id"))
            category  = get_object_or_404(Category, pk=request.POST.get("category_id"))

            if not title or not ISBN:
                raise ValueError("Title and ISBN are required.")

            # Bug fix #4: only pass image kwarg if a file was actually uploaded
            kwargs = dict(
                title=title, summary=summary, ISBN=ISBN,
                publisher=publisher, author=author, category=category,
                total_copies=total, available_copies=total,
            )
            if request.FILES.get("image"):
                kwargs["image"] = request.FILES["image"]

            book = Book.objects.create(**kwargs)
            messages.success(request, f"'{book.title}' added to the catalog.")
            logger.info("Book created: %s by staff %s", book.title, request.user.email)
            return redirect("library:admin_book_list")

        except ValueError as exc:
            messages.error(request, str(exc))
        except Exception as exc:
            logger.exception("Book creation failed: %s", exc)
            messages.error(request, "Could not create book. Please check the form.")

    return render(request, "admin/book_form.html", {
        "authors":    Author.objects.all(),
        "categories": Category.objects.all(),
    })


@staff_required
@require_http_methods(["GET", "POST"])
def admin_book_edit_view(request, book_id):
    book = get_object_or_404(Book, pk=book_id)

    if request.method == "POST":
        try:
            book.title     = request.POST.get("title",     book.title).strip()
            book.summary   = request.POST.get("summary",   book.summary).strip()
            book.ISBN      = request.POST.get("ISBN",      book.ISBN).strip()
            book.publisher = request.POST.get("publisher", book.publisher).strip()
            book.author    = get_object_or_404(Author,   pk=request.POST.get("author_id"))
            book.category  = get_object_or_404(Category, pk=request.POST.get("category_id"))

            if not book.title or not book.ISBN:
                raise ValueError("Title and ISBN are required.")

            new_total = int(request.POST.get("total_copies", book.total_copies))
            diff = new_total - book.total_copies
            book.total_copies     = new_total
            book.available_copies = max(0, book.available_copies + diff)

            if request.FILES.get("image"):
                book.image = request.FILES["image"]

            book.save()
            messages.success(request, f"'{book.title}' updated successfully.")
            logger.info("Book edited: %s by staff %s", book.pk, request.user.email)
            return redirect("library:admin_book_list")

        except ValueError as exc:
            messages.error(request, str(exc))
        except Exception as exc:
            logger.exception("Book edit failed: book_id=%s: %s", book_id, exc)
            messages.error(request, "Could not update book.")

    return render(request, "admin/book_form.html", {
        "book":       book,
        "authors":    Author.objects.all(),
        "categories": Category.objects.all(),
    })


@staff_required
@require_POST
def admin_book_delete_view(request, book_id):
    book  = get_object_or_404(Book, pk=book_id)
    title = book.title

    if Borrow.objects.filter(book=book).exclude(status=Borrow.Status.RETURNED).exists():
        messages.error(request, f"Cannot delete '{title}' — it has active borrows.")
        return redirect("library:admin_book_list")

    try:
        book.delete()
        messages.success(request, f"'{title}' deleted.")
        logger.info("Book deleted: %s by staff %s", book_id, request.user.email)
    except Exception as exc:
        logger.exception("Book delete failed: %s", exc)
        messages.error(request, "Could not delete book.")

    return redirect("library:admin_book_list")


# ===========================================================================
# 11. Admin — Authors & Categories
# ===========================================================================

@staff_required
@require_http_methods(["GET", "POST"])
def admin_author_create_view(request):
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        if not name:
            messages.error(request, "Author name is required.")
            return render(request, "admin/author_form.html")
        try:
            author = Author.objects.create(name=name)
            messages.success(request, f"Author '{author.name}' added.")
            logger.info("Author created: %s by staff %s", author.name, request.user.email)
            return redirect("library:admin_book_list")
        except Exception as exc:
            logger.exception("Author creation failed: %s", exc)
            messages.error(request, "Could not create author.")
    return render(request, "admin/author_form.html")


@staff_required
@require_http_methods(["GET", "POST"])
def admin_category_create_view(request):
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        if not name:
            messages.error(request, "Category name is required.")
            return render(request, "admin/category_form.html")
        try:
            category = Category.objects.create(name=name)
            messages.success(request, f"Category '{category.name}' added.")
            logger.info("Category created: %s by staff %s", category.name, request.user.email)
            return redirect("library:admin_book_list")
        except Exception as exc:
            logger.exception("Category creation failed: %s", exc)
            messages.error(request, "Could not create category.")
    return render(request, "admin/category_form.html")


# ===========================================================================
# 12. Admin — Members
# ===========================================================================

@staff_required
def admin_member_list_view(request):
    query   = request.GET.get("q", "").strip()
    members = Account.objects.filter(is_member=True).order_by("last_name", "first_name")
    if query:
        members = members.filter(
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query)  |
            Q(email__icontains=query)
        )
    page = Paginator(members, 20).get_page(request.GET.get("page"))
    return render(request, "admin/member_list.html", {"page_obj": page, "query": query})


@staff_required
def admin_member_detail_view(request, member_id):
    member       = get_object_or_404(Account, pk=member_id, is_member=True)
    borrows      = Borrow.objects.filter(member=member).select_related("book").order_by("-created_at")
    fines        = Fine.objects.filter(member=member).select_related("borrow__book")
    reservations = Reservation.objects.filter(member=member).select_related("book").order_by("-reserved_on")
    return render(request, "admin/member_detail.html", {
        "member": member, "borrows": borrows,
        "fines": fines, "reservations": reservations,
    })


@staff_required
@require_POST
def admin_toggle_member_active_view(request, member_id):
    member           = get_object_or_404(Account, pk=member_id, is_member=True)
    member.is_active = not member.is_active
    member.save(update_fields=["is_active"])
    state = "enabled" if member.is_active else "disabled"
    messages.success(request, f"{member.get_full_name()}'s account has been {state}.")
    logger.info("Member %s: id=%s by staff %s", state, member_id, request.user.email)
    return redirect("library:admin_member_list")


# ===========================================================================
# 13. Admin — Loans
# ===========================================================================

@staff_required
def admin_loan_list_view(request):
    _apply_overdue_statuses()
    status_filter = request.GET.get("status", "").strip()
    borrows       = Borrow.objects.select_related("book", "member").order_by("-created_at")

    valid_statuses = [s[0] for s in Borrow.Status.choices]
    if status_filter in valid_statuses:
        borrows = borrows.filter(status=status_filter)

    page = Paginator(borrows, 25).get_page(request.GET.get("page"))
    return render(request, "admin/loan_list.html", {
        "page_obj":       page,
        "status_filter":  status_filter,
        "status_choices": Borrow.Status.choices,
    })


@staff_required
@require_POST
def admin_mark_returned_view(request, borrow_id):
    borrow = get_object_or_404(Borrow, pk=borrow_id)

    if borrow.status == Borrow.Status.RETURNED:
        messages.warning(request, "Already marked as returned.")
        return redirect("library:admin_loan_list")

    try:
        with transaction.atomic():
            today              = datetime.date.today()
            borrow.return_date = today
            borrow.status      = Borrow.Status.RETURNED
            borrow.save(update_fields=["return_date", "status"])

            _create_fine_if_overdue(borrow, today)

            Book.objects.filter(pk=borrow.book_id).update(
                available_copies=F("available_copies") + borrow.quantity
            )
            _fulfil_next_reservation(borrow.book)

        messages.success(request, f"Borrow #{borrow_id} marked as returned.")
        logger.info("Staff marked returned: borrow_id=%s by %s", borrow_id, request.user.email)
    except Exception as exc:
        logger.exception("Admin return failed: borrow_id=%s: %s", borrow_id, exc)
        messages.error(request, "Could not process return.")

    return redirect("library:admin_loan_list")


# ===========================================================================
# Inline JSON — Author & Category creation from the book form modal
# ===========================================================================

from django.http import JsonResponse
from django.views.decorators.http import require_POST as _require_POST


@staff_required
@require_POST
def author_create_json(request):
    """
    Called via fetch() from the book form modal.
    Returns {id, name} on success or {error} on failure.
    """
    name = request.POST.get("name", "").strip()
    if not name:
        return JsonResponse({"error": "Author name is required."}, status=400)
    if Author.objects.filter(name__iexact=name).exists():
        return JsonResponse({"error": f"Author '{name}' already exists."}, status=400)
    try:
        author = Author.objects.create(name=name)
        logger.info("Inline author created: %s by staff %s", author.name, request.user.email)
        return JsonResponse({"id": author.pk, "name": author.name})
    except Exception as exc:
        logger.exception("Inline author creation failed: %s", exc)
        return JsonResponse({"error": "Could not create author."}, status=500)


@staff_required
@require_POST
def category_create_json(request):
    """
    Called via fetch() from the book form modal.
    Returns {id, name} on success or {error} on failure.
    """
    name = request.POST.get("name", "").strip()
    if not name:
        return JsonResponse({"error": "Category name is required."}, status=400)
    if Category.objects.filter(name__iexact=name).exists():
        return JsonResponse({"error": f"Category '{name}' already exists."}, status=400)
    try:
        category = Category.objects.create(name=name)
        logger.info("Inline category created: %s by staff %s", category.name, request.user.email)
        return JsonResponse({"id": category.pk, "name": category.name})
    except Exception as exc:
        logger.exception("Inline category creation failed: %s", exc)
        return JsonResponse({"error": "Could not create category."}, status=500)