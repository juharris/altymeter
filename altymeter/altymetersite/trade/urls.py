from django.conf.urls import url

from . import views

urlpatterns = [
    url(r'^collect$', views.collect, name='collect'),
    url(r'^getPairs', views.get_pairs, name='get_pairs'),
    url(r'^stopCollection$', views.stop_collection, name='stop_collection'),
    url(r'^$', views.home, name='home'),
]
