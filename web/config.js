// Dirección del servicio web de SEDATI.
//  - Vacío (''): la API está en el mismo sitio que la página (servidor_web.py en http://localhost:8000).
//  - En AWS: la URL de invocación de Amazon API Gateway, sin la barra final. Ejemplo:
//      apiUrl: 'https://abc123xyz.execute-api.us-east-1.amazonaws.com'
window.SEDATI_CONFIG = {
  apiUrl: ''
};
