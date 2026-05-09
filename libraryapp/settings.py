"""
Django settings for libraryapp project.
"""

from pathlib import Path
from django.contrib.messages import constants as message_constants

BASE_DIR = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------

SECRET_KEY = 'django-insecure-t!qmglfmp1iwiv-*s7^%jj%j@_nrmfw)5_&!+r9xuj_l1(=8z@'
DEBUG      = True
ALLOWED_HOSTS = []


# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'library',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'libraryapp.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'libraryapp.wsgi.application'


# ---------------------------------------------------------------------------
# Custom user model
# ---------------------------------------------------------------------------

AUTH_USER_MODEL = 'library.Account'


# ---------------------------------------------------------------------------
# Auth redirects
# @login_required sends unauthenticated users to LOGIN_URL.
# Our logout view already redirects explicitly, so LOGOUT_REDIRECT_URL
# is a fallback only.
# ---------------------------------------------------------------------------

LOGIN_URL           = '/login/'
LOGIN_REDIRECT_URL  = '/dashboard/'
LOGOUT_REDIRECT_URL = '/login/'


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}


# ---------------------------------------------------------------------------
# Password validation
# ---------------------------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


# ---------------------------------------------------------------------------
# Internationalisation
# ---------------------------------------------------------------------------

LANGUAGE_CODE = 'en-us'
TIME_ZONE     = 'UTC'
USE_I18N      = True
USE_TZ        = True


# ---------------------------------------------------------------------------
# Static & media files
# ---------------------------------------------------------------------------

STATIC_URL       = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']

MEDIA_URL  = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'


# ---------------------------------------------------------------------------
# Flash messages — Bug fix #5
# Map Django's 'error' tag to Bootstrap's 'danger' so alert classes render
# correctly: alert-danger instead of alert-error.
# ---------------------------------------------------------------------------

MESSAGE_TAGS = {
    message_constants.DEBUG:   'secondary',
    message_constants.INFO:    'info',
    message_constants.SUCCESS: 'success',
    message_constants.WARNING: 'warning',
    message_constants.ERROR:   'danger',     # ← key fix: 'error' → 'danger'
}


# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Security hardening  (safe for development; tighten for production)
# ---------------------------------------------------------------------------

# Prevent browsers from MIME-sniffing responses away from the declared content-type
SECURE_CONTENT_TYPE_NOSNIFF = True

# Emit X-XSS-Protection: 1; mode=block on every response
SECURE_BROWSER_XSS_FILTER = True

# Forbid the site from being embedded in any <iframe>
#   XFrameOptionsMiddleware already sends this; being explicit is clearer.
X_FRAME_OPTIONS = 'DENY'

# Cookies are inaccessible to JavaScript — protects session & CSRF cookies
#   NOTE: CSRF_COOKIE_HTTPONLY must remain False so our JS can read it.
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY    = False   # required for JS-based CSRF reads

# Restrict cookies to same-site requests (stops CSRF via third-party sites)
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE    = 'Lax'

# --- Production-only settings (uncomment when deploying over HTTPS) ---
# SECURE_SSL_REDIRECT         = True
# SESSION_COOKIE_SECURE       = True
# CSRF_COOKIE_SECURE          = True
# SECURE_HSTS_SECONDS         = 31536000
# SECURE_HSTS_INCLUDE_SUBDOMAINS = True
# SECURE_HSTS_PRELOAD         = True

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'