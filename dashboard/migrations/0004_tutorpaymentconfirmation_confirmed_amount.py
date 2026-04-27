from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0003_paymentsnapshot'),
    ]

    operations = [
        migrations.AddField(
            model_name='tutorpaymentconfirmation',
            name='confirmed_amount',
            field=models.DecimalField(
                blank=True, decimal_places=2, max_digits=12,
                null=True, verbose_name="Tasdiqlangan summa (so'm)"
            ),
        ),
    ]
