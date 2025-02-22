from django.db import migrations, models
import uuid
import pgvector.django

class Migration(migrations.Migration):
    dependencies = [
        ('semantis_app', '0002_alter_judgment_title'),
        ('semantis_app', '0000_create_vector_extension'),
    ]

    operations = [
        migrations.CreateModel(
            name='TextChunk',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('content', models.TextField()),
                ('chunk_index', models.IntegerField()),
                ('is_embedded', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('judgment', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='chunks', to='semantis_app.judgment')),
            ],
            options={
                'ordering': ['judgment', 'chunk_index'],
                'indexes': [
                    models.Index(fields=['judgment'], name='semantis_ap_judgmen_123456_idx'),
                    models.Index(fields=['is_embedded'], name='semantis_ap_is_embe_123456_idx'),
                ],
            },
        ),
        migrations.AlterField(
            model_name='judgment',
            name='vector_embedding',
            field=pgvector.django.VectorField(blank=True, dimensions=1024, null=True),
        ),
        migrations.AlterField(
            model_name='statute',
            name='vector_embedding',
            field=pgvector.django.VectorField(blank=True, dimensions=1024, null=True),
        ),
    ] 