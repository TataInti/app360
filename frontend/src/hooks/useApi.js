// frontend/src/hooks/useApi.js
import { useState, useCallback } from 'react';
import apiService from '../services/api';

function useApi(endpoint, options = {}) {
  const [data, setData] = useState(options.initialData || null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const execute = useCallback(async (params = {}) => {
    try {
      setLoading(true);
      setError(null);
      const result = await apiService[endpoint](params);
      setData(result);
      return result;
    } catch (err) {
      const errorMessage = err.response?.data?.error || err.message || 'Error desconocido';
      setError(errorMessage);
      throw err;
    } finally {
      setLoading(false);
    }
  }, [endpoint]);

  const reset = useCallback(() => {
    setData(options.initialData || null);
    setError(null);
    setLoading(false);
  }, [options.initialData]);

  return {
    data,
    loading,
    error,
    execute,
    reset
  };
}

export default useApi;