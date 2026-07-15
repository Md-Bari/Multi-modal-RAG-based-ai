from django.db import migrations
from pgvector.django import VectorField

class Migration(migrations.Migration):
    dependencies = [
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.RunSQL(
            sql="ALTER TABLE core_chunk ALTER COLUMN embedding TYPE vector(768);",
            reverse_sql="ALTER TABLE core_chunk ALTER COLUMN embedding TYPE vector(1536);",
        ),
    ]
