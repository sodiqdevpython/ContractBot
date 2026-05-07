from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0002_parenttutorverification_notificationfailure'),
        ('users', '0002_student_created_at_studentcontract_created_at_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='PaymentSnapshot',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('snapshot_date', models.DateField(auto_now_add=True, verbose_name='Sana')),
                ('academic_year', models.CharField(max_length=9, verbose_name="O'quv yili")),
                ('tier_25',  models.PositiveIntegerField(default=0, verbose_name="25% to'lovchilar")),
                ('tier_50',  models.PositiveIntegerField(default=0, verbose_name="50% to'lovchilar")),
                ('tier_75',  models.PositiveIntegerField(default=0, verbose_name="75% to'lovchilar")),
                ('tier_100', models.PositiveIntegerField(default=0, verbose_name="100% to'lovchilar")),
                ('group', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='payment_snapshots',
                    to='users.group',
                    verbose_name='Guruh',
                )),
            ],
            options={
                'verbose_name': "To'lov surati",
                'verbose_name_plural': "To'lov suratlari",
                'ordering': ['-snapshot_date', 'group__name'],
            },
        ),
    ]
