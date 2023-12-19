import datetime
import logging
from datetime import timedelta

from PIL import Image
from celery import shared_task, chain
from django.core.management import call_command
from django.db.models import Sum, ExpressionWrapper, F, fields
from django.http import HttpResponse
from django.utils import timezone
from pyzbar.pyzbar import decode

from core.models import ReportsModel, OrdersModel, ShiftModel, MachineModel, UserRequestsModel, PositionsModel

logger = logging.getLogger('django')


def get_last_or_create_shift(custom_user):
    """
    Retrieves the last shift associated with the given custom user.

    Parameters:
        custom_user (CustomUser): The custom user for which to retrieve the last shift.

    Returns:
        ShiftModel: The last shift associated with the custom user.
        If no previous shift exists or the last shift is ended, a new shift is created and returned.
    """
    last_shift = ShiftModel.objects.filter(user=custom_user).last()
    if not last_shift or last_shift.is_ended():
        new_shift = ShiftModel(user=custom_user)
        new_shift.save()
        logger.info(f"{datetime.datetime.now()} |INFO| User {custom_user} "
                    f"created a new shift #{new_shift.id}")
        return new_shift
    else:
        return last_shift

@shared_task
def save_url(request, order):
    order.hold_url = request.META.get('PATH_INFO')
    order.save()
    return order


def is_all_orders_ended(shift):
    try:
        """
        Проверяет, завершены ли все заказы в указанной смене.
        Возвращает True, если все заказы завершены, иначе False.
        """
        orders = OrdersModel.objects.filter(related_to_shift=shift)
        return not orders or all(order.is_ended() for order in orders)

    except Exception as e:
        # Логирование исключения, если оно произошло
        logger.error(f"{datetime.datetime.now()} |ERROR| An error occurred in is_all_orders_ended: {e}",
                     exc_info=True)

        # Вернуть False в случае ошибки
        return False


def start_new_order(custom_user, shift, selected_machine):
    try:
        machine = MachineModel.objects.get(id=selected_machine)
        machine.is_in_progress = True
        new_order = OrdersModel.objects.create(
            user=custom_user,
            machine=machine,
            related_to_shift=shift,
            start_time=timezone.now()
        )
        machine.order_in_progress = new_order
        machine.save()

        # Логирование события начала нового заказа
        logger.info(
            f"{datetime.datetime.now()} |BACKEND| User {custom_user} started a new order (Order ID: {new_order.id}) on Machine ID: {machine.id}")

        return new_order

    except Exception as e:
        # Логирование исключения, если оно произошло
        logger.error(f"{datetime.datetime.now()} |ERROR| An error occurred in start_new_order: {e}", exc_info=True)

        # Вернуть None в случае ошибки
        return None


def get_order(custom_user, shift, selected_machine):
    try:
        order = OrdersModel.objects.filter(
            user=custom_user,
            related_to_shift=shift,
            machine_id=selected_machine
        ).last()

        # Логирование события получения заказа
        logger.info(
            f"{datetime.datetime.now()} |BACKEND, ORDER| User {custom_user} retrieved the order (Order ID: {order.id}) for Machine ID: {selected_machine}")

        return order

    except Exception as e:
        # Логирование исключения, если оно произошло
        logger.error(f"{datetime.datetime.now()} |ERROR| An error occurred in get_order: {e}", exc_info=True)

        return None


def stop_order(order):
    try:
        machine = MachineModel.objects.get(id=order.machine_id)
        machine.is_in_progress = False
        machine.order_in_progress = None
        order.ended_early = True
        order.end_working_time = timezone.now()
        machine.save()
        order.save()

        # Логирование события остановки заказа
        logger.info(f"{datetime.datetime.now()} |BACKEND| Order {order.id} stopped on Machine ID: {machine.id}")

        return order

    except Exception as e:
        # Логирование исключения, если оно произошло
        logger.error(f"{datetime.datetime.now()} |ERROR| An error occurred in stop_order: {e}", exc_info=True)

        # Вернуть None в случае ошибки
        return None


def add_part_name(order, part_name):
    try:
        order.part_name = part_name
        order.scan_time = timezone.now()
        order.save()

        # Логирование события добавления наименования детали к заказу
        logger.info(f"{datetime.datetime.now()} |BACKEND| Added part name '{part_name}' to Order {order.id}")

        return order

    except Exception as e:
        # Логирование исключения, если оно произошло
        logger.error(f"{datetime.datetime.now()} |ERROR| An error occurred in add_part_name: {e}", exc_info=True)

        # Вернуть None в случае ошибки
        return None


def add_quantity(order, quantity):
    try:
        order.num_parts = quantity
        order.save()

        # Логирование события добавления количества деталей к заказу
        logger.info(f"{datetime.datetime.now()} |BACKEND| Added quantity {quantity} to Order {order.id}")

        return order

    except Exception as e:
        # Логирование исключения, если оно произошло
        logger.error(f"{datetime.datetime.now()} |ERROR| An error occurred in add_quantity: {e}", exc_info=True)

        # Вернуть None в случае ошибки
        return None


def add_start_working_time(order):
    try:
        order.start_working_time = timezone.now()
        order.save()

        # Логирование события добавления времени начала работы над заказом
        logger.info(f"{datetime.datetime.now()} |BACKEND| Added start working time to Order {order.id}")

        return order

    except Exception as e:
        # Логирование исключения, если оно произошло
        logger.error(f"{datetime.datetime.now()} |ERROR| An error occurred in add_start_working_time: {e}",
                     exc_info=True)

        # Вернуть None в случае ошибки
        return None


def add_machine_start_time(order):
    try:
        order.machine_start_time = timezone.now()
        order.save()

        # Логирование события добавления времени начала работы на станке
        logger.info(f"{datetime.datetime.now()} |BACKEND| Added machine start time to Order {order.id}")

        return order

    except Exception as e:
        # Логирование исключения, если оно произошло
        logger.error(f"{datetime.datetime.now()} |ERROR| An error occurred in add_machine_start_time: {e}",
                     exc_info=True)

        # Вернуть None в случае ошибки
        return None


def add_machine_end_time(order):
    try:
        order.machine_end_time = timezone.now()
        order.save()

        # Логирование события добавления времени завершения работы на станке
        logger.info(f"{datetime.datetime.now()} |BACKEND| Added machine end time to Order {order.id}")

        return order

    except Exception as e:
        # Логирование исключения, если оно произошло
        logger.error(f"{datetime.datetime.now()} |ERROR| An error occurred in add_machine_end_time: {e}",
                     exc_info=True)

        # Вернуть None в случае ошибки
        return None


def add_end_working_time(order):
    try:
        order.end_working_time = timezone.now()
        order.save()

        # Логирование события добавления времени завершения работы над заказом
        logger.info(f"{datetime.datetime.now()} |BACKEND| Added end working time to Order {order.id}")

        return order

    except Exception as e:
        # Логирование исключения, если оно произошло
        logger.error(f"{datetime.datetime.now()} |ERROR| An error occurred in add_end_working_time: {e}",
                     exc_info=True)

        # Вернуть None в случае ошибки
        return None


def machine_free(order, status='in_progress'):
    try:
        machine = MachineModel.objects.get(id=order.machine_id)

        if status == 'in_progress':
            machine.order_in_progress = None
            machine.is_in_progress = False
        elif status == 'broken':
            machine.is_broken = False
        elif status == 'both':
            machine.order_in_progress = None
            machine.is_broken = False
            machine.is_in_progress = False

        machine.save()

        # Логирование события освобождения станка
        logger.info(f"{datetime.datetime.now()} |BACKEND| Machine ID: {machine.id} freed (Status: {status})")

        return order

    except Exception as e:
        # Логирование исключения, если оно произошло
        logger.error(f"{datetime.datetime.now()} |ERROR| An error occurred in machine_free: {e}", exc_info=True)

        # Вернуть None в случае ошибки
        return None


def set_on_hold(request, order):
    try:
        order.hold_started = timezone.now()
        order.hold_url = request.META.get('HTTP_REFERER', '/')
        order.save()

        # Логирование события установки заказа на паузу
        logger.info(f"{datetime.datetime.now()} |BACKEND| Order {order.id} set on hold. Hold URL: {order.hold_url}")

        return order

    except Exception as e:
        # Логирование исключения, если оно произошло
        logger.error(f"{datetime.datetime.now()} |ERROR| An error occurred in set_on_hold: {e}", exc_info=True)

        # Вернуть None в случае ошибки
        return None


def remove_hold(order):
    try:
        order.hold_ended = timezone.now()
        order.save()

        # Логирование события снятия заказа с паузы
        logger.info(f"{datetime.datetime.now()} |BACKEND| Hold removed from Order {order.id}")

        return order

    except Exception as e:
        # Логирование исключения, если оно произошло
        logger.error(f"{datetime.datetime.now()} |ERROR| An error occurred in remove_hold: {e}", exc_info=True)

        # Вернуть None в случае ошибки
        return None


def add_report(request, order, custom_user):
    try:
        current_url = request.META.get('HTTP_REFERER', '/')
        ReportsModel.objects.create(
            user=custom_user,
            order=order,
            description=request.POST.get('bug_description'),
            start_time=timezone.now(),
            url=current_url
        )

        machine_id = order.machine.id
        machine = MachineModel.objects.get(id=machine_id)
        machine.is_broken = True
        machine.save()

        order.hold_url = current_url
        order.save()

        # Логирование события добавления отчета о поломке
        logger.info(
            f"{datetime.datetime.now()} |BACKEND| Report added for Order {order.id}. Description: {request.POST.get('bug_description')}")

    except Exception as e:
        # Логирование исключения, если оно произошло
        logger.error(f"{datetime.datetime.now()} |ERROR| An error occurred in add_report: {e}", exc_info=True)

        # Вернуть None в случае ошибки
        return None


def get_all_reports(user):
    try:
        all_reports = ReportsModel.objects.filter(user=user, is_solved=False)

        # Логирование события получения всех не решенных отчетов пользователя
        logger.info(f"{datetime.datetime.now()} |BACKEND| Got all unsolved reports for User {user.id}")

        return all_reports

    except Exception as e:
        # Логирование исключения, если оно произошло
        logger.error(f"{datetime.datetime.now()} |ERROR| An error occurred in get_all_reports: {e}", exc_info=True)

        # Вернуть None в случае ошибки
        return None


def add_request(request, custom_user):
    try:
        UserRequestsModel.objects.create(
            user=custom_user,
            start_time=timezone.now(),
            description=request.POST.get('request_description')
        )

        # Логирование события добавления запроса
        logger.info(
            f"{datetime.datetime.now()} |BACKEND| Request added for User {custom_user.id}. Description: {request.POST.get('request_description')}")

    except Exception as e:
        # Логирование исключения, если оно произошло
        logger.error(f"{datetime.datetime.now()} |ERROR| An error occurred in add_request: {e}", exc_info=True)

        # Вернуть None в случае ошибки
        return None


def count_and_set_reports_duration(order):
    try:
        reports_due_shift = ReportsModel.objects.filter(order=order).filter(
            is_solved=True)

        total_duration = timedelta()
        for report in reports_due_shift:
            one_report_duration = report.end_time - report.start_time
            total_duration += one_report_duration

        order.bugs_time = total_duration
        order.save()

        # Логирование события подсчета и установки продолжительности багов
        logger.info(f"{datetime.datetime.now()} |BACKEND| Counted and set reports duration for Order {order.id}")

        return total_duration

    except Exception as e:
        # Логирование исключения, если оно произошло
        logger.error(f"{datetime.datetime.now()} |ERROR| An error occurred in count_and_set_reports_duration: {e}",
                     exc_info=True)
        # Вернуть None в случае ошибки
        return None


def decode_photo(request):
    """
    API endpoint to /qr-decoder/
    decode image_data
    request: request
    return :str
    """
    image_data = request.FILES.get('image')
    image = Image.open(image_data)
    resized = image.resize((500, 500))
    decoded_qr_img = decode(resized)
    try:
        cropped_data = decoded_qr_img[0].data
        decoded_qr_data = cropped_data.decode('utf-8')
        logger.info(f"{datetime.datetime.now()} |INFO| QR successfully decoded: {decoded_qr_data}")
    except IndexError:
        logger.info(f"{datetime.datetime.now()} |ERROR| QR decoding error")
        decoded_qr_data = 'Ошибка в декодировании'
    return HttpResponse(decoded_qr_data)


@shared_task
def calculate_shift_end_time(shift_id):
    shift = ShiftModel.objects.get(id=shift_id)
    try:
        shift.end_time = timezone.now()
        shift.save()
        # Логирование события расчета времени окончания смены
        logger.info(f"{datetime.datetime.now()} |BACKEND| Calculated shift end time for Shift {shift.id}")

        return shift_id

    except Exception as e:
        # Логирование исключения, если оно произошло
        logger.error(f"{datetime.datetime.now()} |ERROR| An error occurred in calculate_shift_end_time: {e}",
                     exc_info=True)
        # Вернуть None в случае ошибки
        return None


@shared_task
def count_num_ended_orders(shift_id):
    shift = ShiftModel.objects.get(id=shift_id)
    try:
        shift.num_ended_orders = OrdersModel.objects.filter(
            related_to_shift=shift, ended_early=False).count()
        shift.save()
        # Логирование события подсчета количества завершенных заказов в смене
        logger.info(f"{datetime.datetime.now()} |BACKEND| Counted number of ended orders for Shift {shift.id}")

        return shift_id

    except Exception as e:
        # Логирование исключения, если оно произошло
        logger.error(f"{datetime.datetime.now()} |ERROR| An error occurred in count_num_ended_orders: {e}",
                     exc_info=True)
        # Вернуть None в случае ошибки
        return None


@shared_task
def calculate_shift_time_total(shift_id):
    shift = ShiftModel.objects.get(id=shift_id)
    try:
        shift.time_total = shift.end_time - shift.start_time
        shift.save()
        # Логирование события расчета общего времени смены
        logger.info(f"{datetime.datetime.now()} |BACKEND| Calculated total shift time for Shift {shift.id}")

        return shift_id

    except Exception as e:
        # Логирование исключения, если оно произошло
        logger.error(f"{datetime.datetime.now()} |ERROR| An error occurred in calculate_shift_time_total: {e}",
                     exc_info=True)
        # Вернуть None в случае ошибки
        return None


@shared_task
def calculate_total_bugs_time(shift_id):
    shift = ShiftModel.objects.get(id=shift_id)
    try:
        total_bugs_time = OrdersModel.objects.filter(related_to_shift=shift).aggregate(
            total_bugs_time=Sum('bugs_time')
        )['total_bugs_time']

        shift.total_bugs_time = total_bugs_time or timedelta()
        shift.save()
        # Логирование события расчета общего времени багов в смене
        logger.info(f"{datetime.datetime.now()} |BACKEND| Calculated total bugs time for Shift {shift.id}")

        return shift_id

    except Exception as e:
        # Логирование исключения, если оно произошло
        logger.error(f"{datetime.datetime.now()} |ERROR| An error occurred in calculate_total_bugs_time: {e}",
                     exc_info=True)
        # Вернуть None в случае ошибки
        return None


@shared_task
def calculate_good_time(shift_id):
    shift = ShiftModel.objects.get(id=shift_id)
    try:
        duration_expression = ExpressionWrapper(
            F('machine_end_time') - F('machine_start_time'),
            output_field=fields.DurationField()
        )
        orders = OrdersModel.objects.filter(related_to_shift=shift).exclude(
            machine_end_time__isnull=True
        ).exclude(machine_start_time__isnull=True)

        total_good_time = orders.annotate(
            good_time=Sum(duration_expression, output_field=fields.DurationField())
        ).aggregate(total_good_time=Sum('good_time'))['total_good_time']

        shift.good_time = total_good_time or timedelta()
        shift.save()

        # Логирование события расчета общего полезного времени
        logger.info(f"{datetime.datetime.now()} |BACKEND| Calculated total good time for Shift {shift.id}")

        return shift_id

    except Exception as e:
        # Логирование исключения, если оно произошло
        logger.error(f"{datetime.datetime.now()} |ERROR| An error occurred in calculate_good_time: {e}",
                     exc_info=True)
        # Вернуть None в случае ошибки
        return None


@shared_task
def calculate_bad_time(shift_id):
    shift = ShiftModel.objects.get(id=shift_id)
    try:
        total_bad_time = timedelta()

        for order in OrdersModel.objects.filter(related_to_shift=shift):
            if (
                    order.end_working_time is not None and
                    order.scan_time is not None and
                    order.machine_end_time is not None and
                    order.machine_start_time is not None and
                    order.bugs_time is not None
            ):
                bad_time_in_order = (
                        order.end_working_time - order.scan_time -
                        (order.machine_end_time - order.machine_start_time) -
                        order.bugs_time
                )
                total_bad_time += bad_time_in_order

        if shift.bad_time is not None:
            shift.bad_time += total_bad_time
        else:
            shift.bad_time = total_bad_time

        shift.save()
        # Логирование события расчета общего бесполезного времени
        logger.info(f"{datetime.datetime.now()} |BACKEND| Calculated total bad time for Shift {shift.id}")

        return shift_id

    except Exception as e:
        # Логирование исключения, если оно произошло
        logger.error(f"{datetime.datetime.now()} |ERROR| An error occurred in calculate_bad_time: {e}", exc_info=True)
        # Вернуть None в случае ошибки
        return None


@shared_task
def calculate_lost_time(shift_id):
    shift = ShiftModel.objects.get(id=shift_id)
    try:
        chill_time = PositionsModel.objects.get(
            position_name=shift.user.position).chill_time
        total_lost_time = (
                shift.time_total -
                shift.good_time - shift.bad_time -
                shift.total_bugs_time - chill_time
        )
        shift.lost_time = total_lost_time
        shift.save()
        # Логирование события расчета общего потерянного времени
        logger.info(f"{datetime.datetime.now()} |BACKEND| Calculated total lost time for Shift {shift.id}")

        return shift_id

    except Exception as e:
        # Логирование исключения, если оно произошло
        logger.error(f"{datetime.datetime.now()} |ERROR| An error occurred in calculate_lost_time: {e}",
                     exc_info=True)
        # Вернуть None в случае ошибки
        return None


@shared_task
def count_and_end_shift(shift_id):
    try:
        task_chain = (
                calculate_shift_end_time.s(shift_id) |
                count_num_ended_orders.s() |
                calculate_shift_time_total.s() |
                calculate_total_bugs_time.s() |
                calculate_good_time.s() |
                calculate_bad_time.s() |
                calculate_lost_time.s()
        )
        # Запуск цепочки задач
        task_chain.apply_async()
        return shift_id
    except Exception as e:
        logger.error(f"{datetime.datetime.now()} |ERROR| An error occurred in count_and_end_shift: {e}")
