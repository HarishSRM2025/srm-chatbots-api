from django.db import migrations, models


def update_default_model(apps, schema_editor):
    Agent = apps.get_model("agents", "Agent")
    Agent.objects.using(schema_editor.connection.alias).filter(
        model_name__in=["gemini-2.5-flash-lite", "models/gemini-2.5-flash-lite"]
    ).update(model_name="gemini-3.5-flash-lite")


class Migration(migrations.Migration):
    dependencies = [("agents", "0004_gemini_model")]
    operations = [
        migrations.AlterField(
            model_name="agent",
            name="model_name",
            field=models.CharField(default="gemini-3.5-flash-lite", max_length=100),
        ),
        migrations.RunPython(update_default_model, migrations.RunPython.noop),
    ]
