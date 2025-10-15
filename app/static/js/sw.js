// app/static/js/sw.js

console.log('Service Worker: Cargado');

self.addEventListener('push', e => {
    const data = e.data.json();
    console.log('Service Worker: Push Recibido', data);

    const title = data.title || 'ToriaSoft';
    const options = {
        body: data.body,
        icon: data.icon || '/static/images/logo.png', // Asegúrate de tener un logo aquí
        badge: data.badge || '/static/images/badge.png', // Un ícono pequeño para la barra de notificaciones
        data: {
            url: data.url
        }
    };

    e.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', e => {
    const notification = e.notification;
    const urlToOpen = notification.data.url;
    notification.close();

    e.waitUntil(clients.matchAll({ type: 'window' }).then(windowClients => {
        return clients.openWindow(urlToOpen);
    }));
});