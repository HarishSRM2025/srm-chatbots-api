from django.db import migrations, models


def migrate_local_models(apps, schema_editor):
    Agent = apps.get_model("agents", "Agent")
    Agent.objects.using(schema_editor.connection.alias).exclude(
        model_name__startswith="gemini-"
    ).exclude(model_name__startswith="models/gemini-").update(
        model_name="gemini-2.5-flash-lite"
    )


class Migration(migrations.Migration):
    dependencies = [("agents", "0003_agent_allowed_origins")]
    operations = [
        migrations.AlterField(
            model_name="agent",
            name="model_name",
            field=models.CharField(default="gemini-2.5-flash-lite", max_length=100),
        ),
        migrations.RunPython(migrate_local_models, migrations.RunPython.noop),
    ]
