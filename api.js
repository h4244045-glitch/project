import axios from 'axios';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || 'http://localhost:8000';
const API_BASE = `${BACKEND_URL}/api`;

export const api = axios.create({
  baseURL: API_BASE,
  headers: {
    'Content-Type': 'application/json',
  },
});

export const formatINR = (amount) => {
  if (amount === undefined || amount === null) return '₹0';
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
  }).format(amount);
};

export const generateTrip = async (tripData) => {
  const response = await api.post('/generate-trip', tripData);
  return response.data;
};

export const fetchPlacePhoto = async (placeName) => {
  const response = await api.get('/places/photo', {
    params: { query: placeName },
  });
  return response.data.photo_url;
};

export const getStatusChecks = async () => {
  const response = await api.get('/status');
  return response.data;
};

export const createStatusCheck = async (clientName) => {
  const response = await api.post('/status', { client_name: clientName });
  return response.data;
};
