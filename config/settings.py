from pathlib import Path
from django.core.exceptions import ImproperlyConfigured
import os
from dotenv import load_dotenv

load_dotenv()

if os.getenv('DJANGO_ENV', 'development') == 'production':
    load_dotenv(override=True)

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# SECRET_KEY es obligatorio - nunca tiene fallback.
SECRET_KEY = os.getenv('SECRET_KEY')
if not SECRET_KEY:
    raise ImproperlyConfigured(
        'la variable de entorno SECRET_KEY no está configurada.'
        'Definela en .env (desarrollo) o en el entorno de producción.'
    )

# por defecto FALSE - producción nunca expone stack traces por accidente.
DEBUG = os.getenv('DEBUG', 'False') == 'True'

ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'corsheaders',
    'rest_framework',
    'rpc',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# Database

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('DB_NAME', 'postgres'),
        'USER': os.getenv('DB_USER', 'django_app'),
        'PASSWORD': os.getenv('DB_PASSWORD',''),
        'HOST': os.getenv('DB_HOST','localhost'),
        'PORT': os.getenv('DB_PORT', '5432'),
        'OPTIONS': {
            'sslmode': 'require',
        },
    }
}

#No usamos el sisteam de migraciones de Django - el esquema vive en Supabase
class _DisableMigrations:
    def __contains__(self, item):
        return True

    def __getitem__(self, item):
        return None
    
MIGRATION_MODULES = _DisableMigrations()

# REST_FRAMEWORK settings
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'core.jwt_auth.JWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAUL_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'DEFAULT_PARSER_CLASSES': [
        'rest_framework.parsers.JSONParser',
    ],
}

#CORS
# Lista de origenes que pueden llamar a la API desde el navegador
# 
_cors_origins = os.getenv('CORS_ALLOWED_ORIGINS','')
if _cors_origins:
    CORS_ALLOWED_ORIGINS = [
        'http://localhost:3000',   # React / Next.js dev server
        'http://localhost:5173',   # Vite dev server
        'http://localhost:4200',   # Angular dev server
        'http://127.0.0.1:3000',
        'http://127.0.0.1:5173',
    ]

# Solo permite el header Authorizado y Content-Type
CORS_ALLOW_HEADERS = [
    'authorization',
    'content-type',
]

# Solo métodos que usa la API
CORS_ALLOW_METHODS =[
    'POST',
    'OPTIONS',
]

JWT_EXPIRY_HOURS = int(os.getenv('JWT_EXPIRY_HOURS', 24))

# Internationalization
# https://docs.djangoproject.com/en/6.0/topics/i18n/

LANGUAGE_CODE = 'es-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/6.0/howto/static-files/

STATIC_URL = 'static/'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
LOGIN_SP_NAME = os.getenv('LOGIN_SP_NAME', 'sp_usuario_login')