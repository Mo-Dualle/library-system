"""
Django settings for libraryapp project.
"""

import os
from pathlib import Path
from django.contrib.messages import constants as message_constants

BASE_DIR = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------

SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-t!qmglfmp1iwiv-*s7^%jj%j@_nrmfw)5_&!+r9xuj_l1(=8z@')
DEBUG      = os.environ.get('DEBUG', 'True') == 'True'
ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')


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
    'whitenoise.middleware.WhiteNoiseMiddleware',
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
# ---------------------------------------------------------------------------

LOGIN_URL           = '/login/'
LOGIN_REDIRECT_URL  = '/dashboard/'
LOGOUT_REDIRECT_URL = '/login/'


# ---------------------------------------------------------------------------
# Database — PostgreSQL
# Credentials are read from environment variables in production.
# Fallback values are used for local development only.
# ---------------------------------------------------------------------------

DATABASES = {
    'default': {
        'ENGINE':   'django.db.backends.postgresql',
        'NAME':     os.environ.get('DB_NAME',     'library_db_nbu8'),
        'USER':     os.environ.get('DB_USER',     'library_db_nbu8_user'),
        'PASSWORD': os.environ.get('DB_PASSWORD', 'eY5c1YZxUGa3wtY6UnKr77JqDjXdcjFC'),
        'HOST':     os.environ.get('DB_HOST',     'dpg-d7vh786gvqtc73cmhmn0-a'),
        'PORT':     os.environ.get('DB_PORT',     '5432'),
        'OPTIONS': {
            # Keep connections alive for up to 60 s — reduces overhead
            # on repeated requests during development and production.
            'connect_timeout': 10,
        },
        'CONN_MAX_AGE': 60,   # persistent connections (seconds)
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
STATIC_ROOT      = BASE_DIR / 'staticfiles'   # used by collectstatic for deployment

MEDIA_URL  = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'


# ---------------------------------------------------------------------------
# Flash messages
# Maps Django's 'error' tag → Bootstrap's 'danger' class.
# ---------------------------------------------------------------------------

MESSAGE_TAGS = {
    message_constants.DEBUG:   'secondary',
    message_constants.INFO:    'info',
    message_constants.SUCCESS: 'success',
    message_constants.WARNING: 'warning',
    message_constants.ERROR:   'danger',
}


# ---------------------------------------------------------------------------
# Security hardening
# ---------------------------------------------------------------------------

# Prevent MIME-type sniffing
SECURE_CONTENT_TYPE_NOSNIFF = True

# Emit X-XSS-Protection: 1; mode=block
SECURE_BROWSER_XSS_FILTER = True

# Block the site from being embedded in any <iframe>
X_FRAME_OPTIONS = 'DENY'

# Session cookie is HttpOnly — not readable by JavaScript
SESSION_COOKIE_HTTPONLY = True

# CSRF cookie must be readable by JavaScript for fetch()-based requests
CSRF_COOKIE_HTTPONLY = False

# Restrict cookies to same-site requests (mitigates CSRF from third-party sites)
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE    = 'Lax'

# ---------------------------------------------------------------------------
# Production-only settings
# Uncomment these when deploying over HTTPS.
# ---------------------------------------------------------------------------

# SECURE_SSL_REDIRECT            = True
# SESSION_COOKIE_SECURE          = True
# CSRF_COOKIE_SECURE             = True
# SECURE_HSTS_SECONDS            = 31536000   # 1 year
# SECURE_HSTS_INCLUDE_SUBDOMAINS = True
# SECURE_HSTS_PRELOAD            = True
# SECURE_PROXY_SSL_HEADER        = ('HTTP_X_FORWARDED_PROTO', 'https')


# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'