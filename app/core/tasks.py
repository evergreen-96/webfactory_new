import time

from celery import shared_task

@shared_task
def add(x, y):
    print('task1')
    time.sleep(30)

@shared_task()
def my_async_task():
    print(123)
    pass