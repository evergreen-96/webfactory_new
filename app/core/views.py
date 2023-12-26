import os
import traceback
import pandas as pd
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models.expressions import NoneType
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404

from core.buisness import *
from core.forms import ReportEditForm
from core.models import CustomUserModel


logger = logging.getLogger('django')

@login_required(login_url='login')
@user_passes_test(lambda u: u.is_superuser)
def backup(request):
    filename = timezone.now().date()
    backup_dir = "./backups"
    # Создаем директорию, если ее нет
    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir)
    json_filepath = os.path.join(backup_dir, f"{filename}.json")
    excel_filepath = os.path.join(backup_dir, f"{filename}.xlsx")

    # Создаем JSON-бэкап
    with open(json_filepath, 'w') as json_file:
        call_command('dumpdata', 'core', stdout=json_file, indent=3)

    # Преобразуем JSON в DataFrame с использованием pandas
    df = pd.read_json(json_filepath)

    # Создаем объект ExcelWriter для записи в файл Excel
    with pd.ExcelWriter(excel_filepath, engine='xlsxwriter') as writer:
        # Итерируем по уникальным моделям и сохраняем каждую в отдельном листе
        for model in df['model'].unique():
            model_df = df[df['model'] == model]

            # Преобразуем столбец 'fields' в отдельные столбцы с использованием expand
            fields_df = model_df['fields'].apply(pd.Series)

            # Добавляем столбец 'pk'
            fields_df.insert(0, 'pk', model_df['pk'])

            # Добавляем столбец 'model'
            fields_df.insert(0, 'model', model)

            fields_df.to_excel(writer, index=False, sheet_name=model)

    return HttpResponse(excel_filepath)


def login_view(request):
    try:
        if request.method == 'POST':
            username = request.POST.get('username')
            password = request.POST.get('password')

            if not username or not password:
                raise ValueError('Пустое имя пользователя или пароль.')

            user = authenticate(request, username=username, password=password)

            if user is not None:
                login(request, user)
                return redirect('main')
            else:
                messages.error(request, 'Неверное имя пользователя или пароль.')

        return render(request, 'include/login.html')

    except Exception as e:
        logger.error(f'An error occurred in login_view: {e}', exc_info=True)
        messages.error(request, 'Произошла ошибка в процессе входа. Пожалуйста, попробуйте еще раз.')
        return render(request, 'include/login.html')


def logout_view(request):
    """
    Logs out the user by invalidating the current session and redirecting to the 'main' page.
    :param request: The HTTP request object.
    :type request: HttpRequest
    :return: A redirect response to the 'main' page.
    :rtype: HttpResponseRedirect
    """
    logout(request)
    return redirect('main')


@login_required(login_url='/login/')
def pre_shift_view(request):
    """
    Начать смену или выйти из системы
    """

    try:
        custom_user = CustomUserModel.objects.filter(user=request.user.id).last()
        last_shift = ShiftModel.objects.filter(user=custom_user).last()
        is_last_shift_ended = True
        if last_shift:
            is_last_shift_ended = last_shift.is_ended()
        context = {
            'is_last_shift_ended': is_last_shift_ended,
            'user': request.user,
            'custom_user': custom_user,
        }
        if request.method == 'POST':
            if 'start_shift' in request.POST:
                get_last_or_create_shift(custom_user)
                logger.info(f"{datetime.datetime.now()} |INFO| User {custom_user} "
                            f"started-continued a shift")
                return redirect('shift_main_page')

        return render(request, 'include/shift/pre_shift_page.html', context)

    except Exception as e:
        logger.error(f"{datetime.datetime.now()} |ERROR| An error occurred in pre_shift_view: {e}", exc_info=True)

        return HttpResponse('Произошла ошибка')


@login_required(login_url='/login/')
def shift_main_view(request):
    """
    Главная страница смены
    """
    try:
        custom_user = CustomUserModel.objects.get(id=request.user.id)
        machines = custom_user.machine.all()
        shift = get_last_or_create_shift(custom_user)
        shift_id = shift.id
        has_unsolved_reports = ReportsModel.objects.filter(
            order__related_to_shift=shift, is_solved=False
        ).exists()
        context = {
            'user': request.user,
            'custom_user': custom_user,
            'machines': machines,
            'has_unsolved_reports': has_unsolved_reports,
        }

        if request.method == 'POST':
            selected_machine_id = request.POST.get('selected_machine_id')
            request.session['selected_machine_id'] = selected_machine_id

            if 'continue' in request.POST:
                order = get_order(custom_user, shift, selected_machine_id)
                url = order.hold_url

                if type(url) is NoneType:
                    try:
                        url = ReportsModel.objects.filter(order__machine_id=selected_machine_id).last().url
                    except:
                        logger.error(f"An error occurred while getting hold URL: {traceback.format_exc()}")
                        return HttpResponse(f'Произошла ошибка: <br>{traceback.format_exc()} '
                                            f'<br> Обратитесь к администратору, мы все исправим :)'
                                            f'А пока что вернитесь назад используя браузер и экстренно завершив заказ')

                logger.info(f"{datetime.datetime.now()} |INFO| User {custom_user} "
                            f"continued working on machine {selected_machine_id}. Order {order.id} ")
                remove_hold(order)
                return redirect(url)

            if 'start_new' in request.POST:
                new_order = start_new_order(custom_user, shift, selected_machine_id)
                logger.info(
                    f"{datetime.datetime.now()} |INFO| User {custom_user}"
                    f" started a new order #{new_order.id} on machine {selected_machine_id}.")

                return redirect('shift_scan_page')

            if 'stop_working' in request.POST:
                order = get_order(custom_user, shift, selected_machine_id)
                stop_order(order)
                logger.info(f"{datetime.datetime.now()} |INFO| User {custom_user} "
                            f"early stopped working on machine {selected_machine_id}. Order {order.id}")

                return redirect('shift_main_page')

            if 'end_shift' in request.POST:
                if not is_all_orders_ended(shift):
                    messages.error(request, 'Необходимо завершить все заказы!')
                    return redirect('shift_main_page')
                count_and_end_shift.delay(shift_id)
                logger.info(f"{datetime.datetime.now()} |INFO| User {custom_user} ended the shift {shift.id}.")

                return redirect('main')

        return render(request, 'include/shift/main_page.html', context)

    except Exception as e:
        # Логирование исключения, если оно произошло
        logger.error(f"{datetime.datetime.now()} |ERROR| An error occurred in shift_main_view: {e}")

        # Вернуть страницу с сообщением об ошибке или выполнить другие действия по вашему усмотрению
        return HttpResponse('Произошла ошибка')


@login_required(login_url='/login/')
def order_scan_view(request):
    try:
        custom_user = CustomUserModel.objects.get(id=request.user.id)
        shift = get_last_or_create_shift(custom_user)
        order = get_order(custom_user, shift, request.session.get('selected_machine_id'))
        has_unsolved_reports = ReportsModel.objects.filter(
            order__related_to_shift=shift, is_solved=False
        ).exists()
        context = {
            'user': request.user,
            'custom_user': custom_user,
            'shift': shift,
            'order': order,
            'has_unsolved_reports': has_unsolved_reports
        }
        save_url(request, order)

        if request.method == 'POST':
            if 'back' in request.POST:
                machine_free(order, 'in_progress')
                # Логирование события возврата на предыдущую страницу
                logger.info(f"{datetime.datetime.now()} |INFO| User {custom_user} "
                            f"returned to the main shift page from order scanning. "
                            f"Order {order.id} deleted.")
                order.delete()
                return redirect('shift_main_page')

            part_name = request.POST.get('partname')
            add_part_name(order, part_name)

            # Логирование события добавления наименования детали
            logger.info(f"{datetime.datetime.now()} |INFO| User {custom_user} "
                        f"added part name '{part_name}' to the order {order.id}")

            return redirect('shift_qauntity_page')

        return render(request, 'include/shift/scan_name_page.html', context)

    except Exception as e:
        # Логирование исключения, если оно произошло
        logger.error(f"{datetime.datetime.now()} |ERROR| An error occurred in order_scan_view: {e}", exc_info=True)

        # Вернуть страницу с сообщением об ошибке или выполнить другие действия по вашему усмотрению
        return HttpResponse('Произошла ошибка')


@login_required(login_url='/login/')
def order_qauntity_view(request):
    try:
        custom_user = CustomUserModel.objects.get(id=request.user.id)
        shift = get_last_or_create_shift(custom_user)
        order = get_order(custom_user, shift, request.session.get('selected_machine_id'))
        has_unsolved_reports = ReportsModel.objects.filter(
            order__related_to_shift=shift, is_solved=False
        ).exists()

        context = {
            'user': request.user,
            'custom_user': custom_user,
            'shift': shift,
            'order': order,
            'has_unsolved_reports': has_unsolved_reports
        }
        save_url(request, order)

        if request.method == 'POST':
            if 'pause_shift' in request.POST:
                set_on_hold(request, order)

                # Логирование события приостановки работы и перехода к другому станку
                logger.info(f"{datetime.datetime.now()} |INFO| User "
                            f"{custom_user} paused Order {order.id}")

                return redirect('shift_main_page')

            quantity = int(request.POST.get('quantity'))
            add_quantity(order, quantity)
            add_start_working_time(order)

            # Логирование события добавления количества и начала работы над заказом
            logger.info(f"{datetime.datetime.now()} |INFO| User {custom_user} added quantity '{quantity}' "
                        f"and started working on the order {order.id}")

            return redirect('shift_setup_page')

        return render(request, 'include/shift/quantity_page.html', context)

    except Exception as e:
        # Логирование исключения, если оно произошло
        logger.error(f"{datetime.datetime.now()} |ERROR| An error occurred in order_qauntity_view: {e}", exc_info=True)

        return HttpResponse('Произошла ошибка')


@login_required(login_url='/login/')
def order_setup_view(request):
    try:
        custom_user = CustomUserModel.objects.get(id=request.user.id)
        shift = get_last_or_create_shift(custom_user)
        order = get_order(custom_user, shift, request.session.get('selected_machine_id'))
        has_unsolved_reports = ReportsModel.objects.filter(
            order__related_to_shift=shift, is_solved=False
        ).exists()
        save_url(request, order)
        context = {
            'user': request.user,
            'custom_user': custom_user,
            'shift': shift,
            'order': order,
            'has_unsolved_reports': has_unsolved_reports
        }

        if request.method == 'POST':
            if 'pause_shift' in request.POST:
                set_on_hold(request, order)

                # Логирование события приостановки работы и перехода к другому станку
                logger.info(f"{datetime.datetime.now()} |INFO| User "
                            f"{custom_user} paused Order {order.id}")

                return redirect('shift_main_page')

            add_machine_start_time(order)

            # Логирование события добавления времени начала работы над заказом
            logger.info(f"{datetime.datetime.now()} |INFO| User {custom_user}"
                        f" added machine start time for the order {order.id}.")

            return redirect('shift_processing_page')

        return render(request, 'include/shift/setup_page.html', context)

    except Exception as e:
        # Логирование исключения, если оно произошло
        logger.error(f"{datetime.datetime.now()} |ERROR| An error occurred in order_setup_view: {e}", exc_info=True)

        return HttpResponse('Произошла ошибка')


@login_required(login_url='/login/')
def order_processing_view(request):
    try:
        custom_user = CustomUserModel.objects.get(id=request.user.id)
        shift = get_last_or_create_shift(custom_user)
        order = get_order(custom_user, shift, request.session.get('selected_machine_id'))
        has_unsolved_reports = ReportsModel.objects.filter(
            order__related_to_shift=shift, is_solved=False
        ).exists()
        save_url(request, order)
        context = {
            'user': request.user,
            'custom_user': custom_user,
            'shift': shift,
            'order': order,
            'has_unsolved_reports': has_unsolved_reports
        }

        if request.method == 'POST':
            if 'pause_shift' in request.POST:
                set_on_hold(request, order)

                # Логирование события приостановки работы и перехода к другому станку
                logger.info(f"{datetime.datetime.now()} |INFO| User {custom_user} paused Order {order.id}")

                return redirect('shift_main_page')

            add_machine_end_time(order)

            # Логирование события добавления времени окончания работы над заказом
            logger.info(
                f"{datetime.datetime.now()} |INFO| User {custom_user} added machine end time for the order {order.id}.")

            return redirect('shift_ending_page')

        return render(request, 'include/shift/processing_page.html', context)

    except Exception as e:
        # Логирование исключения, если оно произошло
        logger.error(f"{datetime.datetime.now()} |ERROR| An error occurred in order_processing_view: {e}",
                     exc_info=True)

        return HttpResponse('Произошла ошибка')


@login_required(login_url='/login/')
def order_ending_view(request):
    try:
        custom_user = CustomUserModel.objects.get(id=request.user.id)
        shift = get_last_or_create_shift(custom_user)
        order = get_order(custom_user, shift, request.session.get('selected_machine_id'))
        has_unsolved_reports = ReportsModel.objects.filter(
            order__related_to_shift=shift, is_solved=False
        ).exists()
        save_url(request, order)
        context = {
            'user': request.user,
            'custom_user': custom_user,
            'shift': shift,
            'order': order,
            'has_unsolved_reports': has_unsolved_reports
        }

        if request.method == 'POST':
            if 'pause_shift' in request.POST:
                set_on_hold(request, order)

                # Логирование события приостановки работы и перехода к другому станку
                logger.info(f"{datetime.datetime.now()} |INFO| User {custom_user} paused Order {order.id}")

                return redirect('shift_main_page')
            add_end_working_time(order)
            machine_free(order)
            count_and_set_reports_duration(order)

            logger.info(f"{datetime.datetime.now()} |INFO| User {custom_user} ended work on Order {order.id}")

            return redirect('shift_main_page')

        return render(request, 'include/shift/ending_order_page.html', context)

    except Exception as e:
        # Логирование исключения, если оно произошло
        logger.error(f"{datetime.datetime.now()} |ERROR| An error occurred in order_ending_view: {e}", exc_info=True)

        return HttpResponse('Произошла ошибка')


@login_required(login_url='/login/')
def report_send(request):
    try:
        custom_user = CustomUserModel.objects.get(id=request.user.id)
        shift = get_last_or_create_shift(custom_user)
        order = get_order(custom_user, shift, request.session.get('selected_machine_id'))

        if request.method == 'POST':
            add_report(request, order, custom_user)
            logger.info(f"{datetime.datetime.now()} |INFO| User {custom_user} sent a report for Order {order.id}")

            return HttpResponse('Report sent successfully')
        else:
            # Логирование неправильного запроса
            logger.warning(
                f"{datetime.datetime.now()} |WARNING| User {custom_user} made a bad request to report_send view")
            return HttpResponse('Bad request')

    except Exception as e:
        # Логирование исключения, если оно произошло
        logger.error(f"{datetime.datetime.now()} |ERROR| An error occurred in report_send: {e}", exc_info=True)

        return HttpResponse('An error occurred')


@login_required(login_url='/login/')
def reports_view(request):
    try:
        custom_user = CustomUserModel.objects.get(id=request.user.id)
        user_reports = ReportsModel.objects.filter(user=custom_user).order_by('-start_time').order_by('is_solved')
        form = ReportEditForm()

        context = {
            'user_reports': user_reports,
            'form': form,
            'custom_user': custom_user
        }

        # POST to solve report and set is_broken False
        if request.method == 'POST':
            report_id = request.POST.get('bug_id')
            report = get_object_or_404(ReportsModel, pk=report_id)
            form = ReportEditForm(request.POST, instance=report)
            if form.is_valid():
                if form.cleaned_data['is_solved']:
                    report.end_time = timezone.now()
                form.save()
                machine_free(report.order, status='broken')

                logger.info(f"{datetime.datetime.now()} |INFO| User {custom_user} solved Report {report.id}")

                return JsonResponse({'status': 'success'})

        return render(request, 'include/reports_page.html', context)

    except Exception as e:
        # Логирование исключения, если оно произошло
        logger.error(f"{datetime.datetime.now()} |ERROR| An error occurred in reports_view: {e}", exc_info=True)

        return HttpResponse('An error occurred')


@login_required(login_url='/login/')
def request_send(request):
    try:
        custom_user = CustomUserModel.objects.get(id=request.user.id)

        if request.method == 'POST':
            add_request(request, custom_user)
            logger.info(f"{datetime.datetime.now()} |INFO| User {custom_user} sent a request")
            return HttpResponse('Request sent successfully')
        else:
            # Логирование неправильного запроса
            logger.warning(
                f"{datetime.datetime.now()} |WARNING| User {custom_user} made a bad request to request_send view")
            return HttpResponse('Bad request')

    except Exception as e:
        # Логирование исключения, если оно произошло
        logger.error(f"{datetime.datetime.now()} |ERROR| An error occurred in request_send: {e}", exc_info=True)

        return HttpResponse('An error occurred')
