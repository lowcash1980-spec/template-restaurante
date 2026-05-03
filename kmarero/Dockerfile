FROM nginx:alpine

COPY . /usr/share/nginx/html

EXPOSE 80

# envsubst sustituye las variables del .env en el HTML al arrancar el contenedor.
# Las variables de JavaScript (${item.name} etc.) no se tocan porque no están en la lista.
CMD ["/bin/sh", "-c", \
  "envsubst '$NOMBRE_RESTAURANTE $CIUDAD $DIRECCION $TELEFONO $PIN_ADMIN $ESLOGAN_RESTAURANTE $BACKEND_URL $CORE_URL' \
  < /usr/share/nginx/html/index.html.template \
  > /usr/share/nginx/html/index.html \
  && nginx -g 'daemon off;'"]
