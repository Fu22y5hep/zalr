from django.db import migrations

class Migration(migrations.Migration):
    initial = True

    dependencies = []

    def create_vector_extension(apps, schema_editor):
        # Skip if not PostgreSQL
        if schema_editor.connection.vendor != 'postgresql':
            return
        # Create the vector extension
        schema_editor.execute('CREATE EXTENSION IF NOT EXISTS vector')

    def reverse_vector_extension(apps, schema_editor):
        if schema_editor.connection.vendor != 'postgresql':
            return
        schema_editor.execute('DROP EXTENSION IF EXISTS vector')

    operations = [
        migrations.RunPython(create_vector_extension, reverse_vector_extension),
    ] 