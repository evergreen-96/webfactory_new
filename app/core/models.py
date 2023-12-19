from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractUser
from django.db import models

User = get_user_model()


class MachineTypesModel(models.Model):
    machine_type = models.CharField(max_length=512, verbose_name='Тип станка')

    def __str__(self):
        return self.machine_type

    class Meta:
        verbose_name = 'Тип станка'
        verbose_name_plural = 'Типы станков'


class MachineModel(models.Model):
    machine_type = models.ForeignKey(MachineTypesModel, on_delete=models.CASCADE, verbose_name='Тип станка')
    machine_name = models.CharField(max_length=512, verbose_name='Название станка')
    is_broken = models.BooleanField(default=False, verbose_name='Сломан?')
    is_in_progress = models.BooleanField(default=False, verbose_name='В работе?')
    order_in_progress = models.ForeignKey('OrdersModel', on_delete=models.CASCADE,
                                          default=None, null=True, blank=True)

    def __str__(self):
        return f'{self.machine_name} | Тип: {self.machine_type}'

    class Meta:
        verbose_name = 'Станок'
        verbose_name_plural = 'Станки'


class RoleModel(models.Model):
    role_name = models.CharField(
        choices=[('worker', 'worker'), ('admin', 'admin')], max_length=64)

    def __str__(self):
        return self.role_name

    class Meta:
        verbose_name = 'Роль'
        verbose_name_plural = 'Роли'


class WorkingAreaModel(models.Model):
    area_name = models.CharField(max_length=128, verbose_name='Рабочее место')

    def __str__(self):
        return self.area_name

    class Meta:
        verbose_name = 'Рабочее место'
        verbose_name_plural = 'Рабочие места'


class PositionsModel(models.Model):
    position_name = models.CharField(max_length=128, verbose_name='Должность')
    chill_time = models.DurationField(max_length=128, verbose_name='Время отдыха')

    def __str__(self):
        return self.position_name

    class Meta:
        verbose_name = 'Должность'
        verbose_name_plural = 'Должности'


class CustomUserModel(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, verbose_name='Пользователь')
    phone_number = models.CharField(max_length=64, unique=True, verbose_name='Номер телефона')
    role = models.ForeignKey(RoleModel, on_delete=models.CASCADE, verbose_name='Роль')
    position = models.ForeignKey(PositionsModel, on_delete=models.CASCADE, verbose_name='Должность')
    working_area = models.ForeignKey(WorkingAreaModel,
                                     on_delete=models.CASCADE, verbose_name='Рабочее место')
    machine = models.ManyToManyField(MachineModel, blank=True, verbose_name='Станок')


    def __str__(self):
        return self.user.username

    class Meta:
        verbose_name = 'Пользователь'
        verbose_name_plural = 'Пользователи'


class ShiftModel(models.Model):
    user = models.ForeignKey(CustomUserModel, on_delete=models.CASCADE, verbose_name='Пользователь')
    start_time = models.DateTimeField(auto_now_add=True, editable=True, verbose_name='Начало смены')
    end_time = models.DateTimeField(blank=True, null=True, verbose_name='Конец смены')
    num_ended_orders = models.PositiveIntegerField(default=0, verbose_name='Количество завершенных заказов')
    time_total = models.DurationField(blank=True, null=True, verbose_name='Общее время смены')
    good_time = models.DurationField(blank=True, null=True, verbose_name='Полезное время')
    bad_time = models.DurationField(blank=True, null=True, verbose_name='Бесполезное время')
    lost_time = models.DurationField(blank=True, null=True, verbose_name='Потерянное время')
    total_bugs_time = models.DurationField(blank=True, null=True, verbose_name='Общее время поломок')

    def formatted_start_time(self):
        return self.start_time.strftime('%Y-%m-%d %H:%M:%S') if self.start_time else None

    def formatted_end_time(self):
        return self.end_time.strftime('%Y-%m-%d %H:%M:%S') if self.end_time else None

    def is_ended(self):
        return self.end_time is not None

    def __str__(self):
        return (f'ID: {self.id}  Start Time: {self.formatted_start_time()}')

    class Meta:
        verbose_name = 'Смена'
        verbose_name_plural = 'Смены'


class OrdersModel(models.Model):
    user = models.ForeignKey(CustomUserModel, on_delete=models.CASCADE, verbose_name='Пользователь')
    machine = models.ForeignKey(MachineModel, on_delete=models.CASCADE, blank=True, null=True, verbose_name='Станок')
    related_to_shift = models.ForeignKey(ShiftModel, related_name='stat_orders',
                                         on_delete=models.CASCADE, verbose_name='Смена')
    part_name = models.TextField(max_length=1000,verbose_name='Название детали')
    num_parts = models.PositiveIntegerField(default=0, verbose_name='Количество деталей')
    start_time = models.DateTimeField(blank=True, null=True, verbose_name='Начало работы')
    scan_time = models.DateTimeField(blank=True, null=True, verbose_name='Время сканирования')
    start_working_time = models.DateTimeField(blank=True, null=True, verbose_name='Начало работы с деталью')
    machine_start_time = models.DateTimeField(blank=True, null=True, verbose_name='Начало работы на станке')
    machine_end_time = models.DateTimeField(blank=True, null=True, verbose_name='Конец работы на станке')
    end_working_time = models.DateTimeField(blank=True, null=True, verbose_name='Конец работы с деталью')
    bugs_time = models.DurationField(blank=True, null=True, verbose_name='Время поломок')
    ended_early = models.BooleanField(default=False, verbose_name='Завершено раньше?')
    hold_started = models.DateTimeField(blank=True, null=True, verbose_name='Начало удержания')
    hold_url = models.CharField(max_length=256, blank=True, null=True, verbose_name='Ссылка на удержание')
    hold_ended = models.DateTimeField(blank=True, null=True, verbose_name='Конец удержания')


    def __str__(self):
        return (f'ID: {self.id} | Смена: {self.related_to_shift} | Деталь: {self.part_name} '
                f'| Количество: {self.num_parts} | Рабочий: {self.user} | '
                f' Станок: {self.machine}')

    def is_ended(self):
        return self.end_working_time is not None

    class Meta:
        verbose_name = 'Заказ'
        verbose_name_plural = 'Заказы'


class ReportsModel(models.Model):
    user = models.ForeignKey(CustomUserModel, on_delete=models.CASCADE, verbose_name='Пользователь')
    order = models.ForeignKey(OrdersModel, on_delete=models.CASCADE,
                              null=True, blank=True, verbose_name='Заказ')
    description = models.CharField(max_length=1028, verbose_name='Описание')
    start_time = models.DateTimeField(auto_now_add=True, verbose_name='Начало')
    end_time = models.DateTimeField(blank=True, null=True, verbose_name='Конец')
    is_solved = models.BooleanField(default=False, verbose_name='Решено?')
    url = models.CharField(max_length=128, blank=True, null=True, verbose_name='Откуда отправлен')

    def __str__(self):
        order_info = f'Order: {self.order.part_name}' if self.order else 'No associated order'
        solved_status = 'Solved' if self.is_solved else 'Not Solved'

        return f'ID: {self.id} | Report by {self.user} | {order_info} | Description: {self.description} | Status: {solved_status}'

    class Meta:
        verbose_name = 'Сообщение о проблеме'
        verbose_name_plural = 'Сообщения о проблеме'


class UserRequestsModel(models.Model):
    user = models.ForeignKey(CustomUserModel, on_delete=models.CASCADE, verbose_name='Пользователь')
    description = models.CharField(max_length=1028, verbose_name='Описание')
    start_time = models.DateTimeField(auto_now_add=True, verbose_name='Начало')
    end_time = models.DateTimeField(blank=True, null=True, verbose_name='Конец')
    is_solved = models.BooleanField(default=False, verbose_name='Решено?')


    def __str__(self):
        is_solved = 'Открыт'
        if self.is_solved:
            is_solved = 'Закрыт'
        return f'{self.start_time.date()} | {self.description} | {is_solved}'

    class Meta:
        verbose_name = 'Запрос пользователя'
        verbose_name_plural = 'Запросы пользователя'