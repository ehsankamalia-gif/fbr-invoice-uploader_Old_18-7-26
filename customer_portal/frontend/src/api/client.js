import axios from 'axios';

// Django's CSRF cookie/header names differ from axios's Angular-style
// defaults (XSRF-TOKEN / X-XSRF-TOKEN) - must override both or CSRF
// silently fails on every POST/PUT/DELETE.
const api = axios.create({
  baseURL: '/api/v1/',
  withCredentials: true,
  xsrfCookieName: 'csrftoken',
  xsrfHeaderName: 'X-CSRFToken',
});

export default api;
