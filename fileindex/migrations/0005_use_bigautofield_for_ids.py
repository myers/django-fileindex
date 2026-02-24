# Generated manually to ensure consistent BigAutoField usage across projects

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("fileindex", "0004_remove_indexedfile_visual_media_requires_dimensions_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="filepath",
            name="id",
            field=models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID"),
        ),
        migrations.AlterField(
            model_name="indexedfile",
            name="id",
            field=models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID"),
        ),
    ]
