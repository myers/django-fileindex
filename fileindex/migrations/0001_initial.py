# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="FilePath",
            fields=[
                (
                    "id",
                    models.AutoField(
                        primary_key=True,
                        serialize=False,
                        auto_created=True,
                        verbose_name="ID",
                    ),
                ),
                ("mtime", models.DateTimeField()),
                ("ctime", models.DateTimeField()),
                ("path", models.CharField(max_length=2048, db_index=True)),
                ("created_at", models.DateTimeField()),
            ],
        ),
        migrations.CreateModel(
            name="IndexedFile",
            fields=[
                (
                    "id",
                    models.AutoField(
                        primary_key=True,
                        serialize=False,
                        auto_created=True,
                        verbose_name="ID",
                    ),
                ),
                ("size", models.IntegerField()),
                ("sha1", models.CharField(max_length=255, db_index=True, null=True)),
                ("sha512", models.CharField(max_length=255, db_index=True, null=True)),
                (
                    "mime_type",
                    models.CharField(max_length=255, db_index=True, null=True),
                ),
                ("first_seen", models.DateTimeField()),
                ("corrupt", models.NullBooleanField(default=None)),
            ],
        ),
        migrations.AddField(
            model_name="filepath",
            name="indexedfile",
            field=models.ForeignKey(
                to="fileindex.IndexedFile", null=False, on_delete=models.CASCADE
            ),
        ),
    ]
