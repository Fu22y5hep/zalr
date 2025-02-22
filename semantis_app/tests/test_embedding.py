import os
import uuid
import pytest
from django.test import TestCase
from semantis_app.utils.embedding import EmbeddingGenerator

# Set Django settings module for tests
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'semantis_app.tests.test_settings')

@pytest.fixture(autouse=True)
def debug_env():
    """Print environment variables for debugging"""
    print("\nDebug: Environment variables:")
    print(f"SUPABASE_URL = {os.getenv('SUPABASE_URL')}")
    print(f"SUPABASE_PUBLIC_KEY = {os.getenv('SUPABASE_PUBLIC_KEY')}")

@pytest.fixture
def emb_gen():
    return EmbeddingGenerator()

@pytest.fixture
def judgment_id():
    # Use a proper UUID for testing
    return str(uuid.uuid4())

def test_fetch_text_from_db(emb_gen, judgment_id):
    # TODO: We need to create test data in the database first
    # For now, this test will fail because the judgment doesn't exist
    with pytest.raises(ValueError, match="No record found"):
        text = emb_gen.fetch_text_from_db(judgment_id)

def test_full_pipeline(emb_gen, judgment_id):
    # TODO: We need to create test data in the database first
    # For now, this test will fail because the judgment doesn't exist
    with pytest.raises(ValueError, match="No record found"):
        results = emb_gen.process_judgment_and_store(judgment_id, {"doc_id": judgment_id})
