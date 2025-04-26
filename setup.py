from setuptools import setup, find_packages

setup(
    name="zalr",
    version="0.1.0",
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        'django>=5.1.6',
        'djangorestframework',
        'django-cors-headers',
        'psycopg2-binary',
        'openai',
        'supabase',
        'python-dotenv',
    ],
    python_requires='>=3.8',
) 