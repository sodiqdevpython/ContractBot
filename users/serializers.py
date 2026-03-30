from rest_framework import serializers
from .models import Student, Parent, StudentParent, Payment, Group, StudentContract

class GroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = Group
        fields = ['id', 'name']

# YANGI QO'SHILDI
class StudentContractSerializer(serializers.ModelSerializer):
    debt_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = StudentContract
        fields = ['id', 'academic_year', 'course_level', 'is_grant', 'contract_amount', 'paid_amount', 'debt_amount']

class PaymentSerializer(serializers.ModelSerializer):
    # Endi academic_year va course_level malumotlari contractdan olinadi
    academic_year = serializers.CharField(source='contract.academic_year', read_only=True)
    course_level = serializers.IntegerField(source='contract.course_level', read_only=True)
    
    class Meta:
        model = Payment
        fields = ['id', 'amount', 'payment_date', 'academic_year', 'course_level']

class ParentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Parent
        fields = ['phone_number', 'full_name', 'telegram_id', 'tg_username', 'is_blacklisted']

class StudentParentSerializer(serializers.ModelSerializer):
    parent = ParentSerializer(read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    role_display = serializers.CharField(source='get_role_display', read_only=True)
    class Meta:
        model = StudentParent
        fields = ['parent', 'role', 'role_display', 'status', 'status_display']

class StudentProfileSerializer(serializers.ModelSerializer):
    group = GroupSerializer(read_only=True)
    # Bot buzilmasligi uchun Student dagi all_payments property'sini beramiz
    payments = PaymentSerializer(source='all_payments', many=True, read_only=True)
    parents = StudentParentSerializer(many=True, read_only=True)
    contracts = StudentContractSerializer(many=True, read_only=True)
    
    # Umumiy xisob kitoblar
    total_contract_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    paid_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    debt_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = Student
        fields = [
            'student_id', 'full_name', 'group', 
            'total_contract_amount', 'paid_amount', 'debt_amount',
            'contracts', 'telegram_id', 'tg_username', 'tg_language', 
            'payments', 'parents'
        ]