from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0001_initial'),
        ('users', '0002_student_created_at_studentcontract_created_at_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ParentTutorVerification',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('verified_at', models.DateTimeField(auto_now_add=True, verbose_name='Tasdiqlagan vaqti')),
                ('note', models.TextField(blank=True, verbose_name='Izoh')),
                ('student_parent', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='tutor_verification',
                    to='users.studentparent',
                    verbose_name='Talaba–Ota-ona',
                )),
                ('verified_by', models.ForeignKey(
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='parent_verifications',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Tasdiqlagan tutor',
                )),
            ],
            options={
                'verbose_name': 'Tutor ota-ona tasdiqi',
                'verbose_name_plural': 'Tutor ota-ona tasdiqlari',
            },
        ),
        migrations.CreateModel(
            name='NotificationFailure',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('telegram_id', models.BigIntegerField(verbose_name='Telegram ID')),
                ('recipient_type', models.CharField(
                    choices=[('student', 'Talaba'), ('parent', 'Ota-ona')],
                    max_length=10,
                    verbose_name='Kim',
                )),
                ('error_code', models.IntegerField(blank=True, null=True, verbose_name='Xato kodi')),
                ('error_description', models.TextField(verbose_name='Xato tavsifi')),
                ('fail_count', models.PositiveIntegerField(default=1, verbose_name='Xato soni')),
                ('last_failed_at', models.DateTimeField(auto_now=True, verbose_name='Oxirgi xato vaqti')),
                ('is_otp', models.BooleanField(default=False, verbose_name='OTP yuborishda xatomi?')),
                ('campaign', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    to='users.notificationcampaign',
                    verbose_name='Kampaniya',
                )),
                ('parent', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='notification_failures',
                    to='users.parent',
                    verbose_name='Ota-ona',
                )),
                ('student', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='notification_failures',
                    to='users.student',
                    verbose_name='Talaba',
                )),
            ],
            options={
                'verbose_name': 'Xabarnoma xatosi',
                'verbose_name_plural': 'Xabarnoma xatolari',
                'ordering': ['-last_failed_at'],
                'unique_together': {('telegram_id', 'recipient_type')},
            },
        ),
    ]
