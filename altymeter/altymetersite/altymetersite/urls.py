from django.conf.urls import include, url
from django.contrib import admin

from altymeter.altymetersite.trade import urls as trade_urls
from altymeter.altymetersite.trade.views import home

urlpatterns = [
    url(r'^admin/?', admin.site.urls, name='admin'),

    url(r'^$', home, name='home'),

    url(r'^', include(trade_urls, namespace='trade')),
]
