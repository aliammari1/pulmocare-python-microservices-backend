FROM nginx:alpine

COPY index.html /usr/share/nginx/html/
COPY script.js /usr/share/nginx/html/

# Configure Nginx to proxy requests to Elasticsearch
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
