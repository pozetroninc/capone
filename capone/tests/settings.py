import os


DEBUG = True

INSTALLED_APPS = (
    'capone.tests',
    'capone',
    'django.contrib.sessions',
    'django.contrib.contenttypes',
    'django.contrib.auth',
)

SECRET_KEY = 'secretkey'

TEMPLATE_DIRS = (os.path.join(os.path.dirname(__file__), 'templates'),)

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': 'sqlite://',  # test with in-memory sqlite
    },
}

ALLOWED_HOSTS = []

MIDDLEWARE_CLASSES = (
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.contrib.auth.middleware.SessionAuthenticationMiddleware',
)
SESSION_ENGINE = 'django.contrib.sessions.backends.db'
