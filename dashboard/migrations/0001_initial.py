from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('users', '0002_student_created_at_studentcontract_created_at_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='TutorPaymentConfirmation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('confirmed_at', models.DateTimeField(auto_now_add=True, verbose_name='Tasdiqlagan vaqti')),
                ('is_active', models.BooleanField(default=True, verbose_name='Faolmi?')),
                ('note', models.TextField(blank=True, verbose_name='Izoh')),
                ('contract', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='tutor_confirmations',
                    to='users.studentcontract',
                    verbose_name='Shartnoma',
                )),
                ('confirmed_by', models.ForeignKey(
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='payment_confirmations',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Tasdiqlagan tutor',
                )),
            ],
            options={
                'verbose_name': "Tutor to'lov tasdiqi",
                'verbose_name_plural': "Tutor to'lov tasdiqlari",
                'ordering': ['-confirmed_at'],
            },
        ),
    ]
