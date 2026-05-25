from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cambridge_practice', '0003_answerkey_practiceresult'),
    ]

    operations = [
        migrations.AddField(
            model_name='practiceresult',
            name='band_score',
            field=models.DecimalField(blank=True, decimal_places=1, max_digits=3, null=True),
        ),
    ]
