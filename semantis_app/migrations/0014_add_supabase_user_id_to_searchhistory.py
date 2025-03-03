# Generated by Django 5.1.6 on 2025-03-02 10:09

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("semantis_app", "0013_rename_user_id_to_supabase_user_id"),
    ]

    operations = [
        migrations.AddField(
            model_name="searchhistory",
            name="supabase_user_id",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddIndex(
            model_name="searchhistory",
            index=models.Index(
                fields=["supabase_user_id"], name="semantis_ap_supabas_d500e0_idx"
            ),
        ),
    ]
