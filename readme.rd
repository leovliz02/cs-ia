1) Open command prompt, Create Virtual Env
python -m venv venv
.\venv\Scripts\activate

cd cs-ia-main
.\compsci_ia_venv\bin\activate

2) Install yFinance
python -m pip install Django
python -m pip install djangorestframework

3) Create Django project (One time)
django-admin startproject latestdemand
cd latestdemand
python manage.py startapp core

4) Run from root c:/apps/leah/cs-ia
python manage.py migrate
python manage.py createsuperuser
admin
admin@admin.com
admin

newemployee / onetwo34

5) 
python manage.py runserver
