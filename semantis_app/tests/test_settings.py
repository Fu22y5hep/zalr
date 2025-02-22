import os
from pathlib import Path
from dotenv import load_dotenv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Load environment variables from .env file in project root
load_dotenv(os.path.join(BASE_DIR, '.env'))

# Basic Django settings required for testing
SECRET_KEY = 'test-key-not-for-production'
DEBUG = True

# Database settings for testing (use SQLite in memory)
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

# Supabase settings
SUPABASE_API_URL = os.getenv('SUPABASE_URL')  # This should be the https:// URL
SUPABASE_DB_URL = os.getenv('SUPABASE_DB_URL')  # This is the postgresql:// URL
SUPABASE_KEY = os.getenv('SUPABASE_PUBLIC_KEY')
SUPABASE_SERVICE_ROLE_KEY = os.getenv('SUPABASE_SERVICE_ROLE_KEY')

# Required for Django setup
INSTALLED_APPS = [
    'django.contrib.contenttypes',
    'django.contrib.auth',
    'semantis_app',
]

# Minimal middleware
MIDDLEWARE = []

# Required for Django setup
ROOT_URLCONF = 'zalr_backend.urls' 