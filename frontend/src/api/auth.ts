import axios from 'axios';
import { apiClient } from './client';
import type { User } from '../state/auth';

export interface LoginRequest {
  email: string;
  password: string;
}

export interface LoginResponse {
  user: User;
  token: string;
  refreshToken?: string;
}

export interface RefreshTokenRequest {
  refreshToken: string;
}

export interface RefreshTokenResponse {
  token: string;
  refreshToken?: string;
}

// Auth API service
export class AuthAPI {
  private static readonly AUTH_ENDPOINTS = {
    LOGIN: '/auth/login',
    LOGOUT: '/auth/logout',
    REFRESH: '/auth/refresh',
    ME: '/auth/me'
  };

  static async login(credentials: LoginRequest): Promise<LoginResponse> {
    try {
      const response = await apiClient.post<LoginResponse>(
        AuthAPI.AUTH_ENDPOINTS.LOGIN,
        credentials
      );
      return response.data;
    } catch (error) {
      if (axios.isAxiosError(error) && error.response) {
        const message = error.response.data?.message || 'Invalid credentials';
        throw new Error(message);
      }
      throw new Error('Login failed. Please try again.');
    }
  }

  static async logout(token: string): Promise<void> {
    try {
      await apiClient.post(
        AuthAPI.AUTH_ENDPOINTS.LOGOUT,
        {},
        {
          headers: {
            Authorization: `Bearer ${token}`
          }
        }
      );
    } catch (error) {
      // Logout should not throw errors to the UI
      console.error('Logout error:', error);
    }
  }

  static async refreshToken(refreshToken: string): Promise<RefreshTokenResponse> {
    try {
      const response = await apiClient.post<RefreshTokenResponse>(
        AuthAPI.AUTH_ENDPOINTS.REFRESH,
        { refreshToken }
      );
      return response.data;
    } catch (error) {
      throw new Error('Session expired. Please login again.');
    }
  }

  static async getCurrentUser(token: string): Promise<User> {
    try {
      const response = await apiClient.get<User>(
        AuthAPI.AUTH_ENDPOINTS.ME,
        {
          headers: {
            Authorization: `Bearer ${token}`
          }
        }
      );
      return response.data;
    } catch (error) {
      throw new Error('Failed to fetch user information');
    }
  }

  static setAuthToken(token: string) {
    apiClient.defaults.headers.common['Authorization'] = `Bearer ${token}`;
  }

  static clearAuthToken() {
    delete apiClient.defaults.headers.common['Authorization'];
  }
}

// Mock API for development
export class MockAuthAPI {
  private static readonly MOCK_USERS = [
    {
      id: '1',
      email: 'demo@example.com',
      name: 'Demo User',
      role: 'user'
    },
    {
      id: '2', 
      email: 'admin@example.com',
      name: 'Admin User',
      role: 'admin'
    }
  ];

  static async login(credentials: LoginRequest): Promise<LoginResponse> {
    // Simulate network delay
    await new Promise(resolve => setTimeout(resolve, 1000));
    
    const user = MockAuthAPI.MOCK_USERS.find(
      u => u.email === credentials.email
    );
    
    if (!user || (credentials.password !== 'demo123' && credentials.password !== 'admin123')) {
      throw new Error('Invalid email or password');
    }
    
    const token = `mock-jwt-token-${user.id}-${Date.now()}`;
    
    return {
      user,
      token,
      refreshToken: `refresh-${token}`
    };
  }

  static async logout(): Promise<void> {
    await new Promise(resolve => setTimeout(resolve, 200));
  }

  static async refreshToken(): Promise<RefreshTokenResponse> {
    await new Promise(resolve => setTimeout(resolve, 500));
    
    const token = `mock-jwt-token-refresh-${Date.now()}`;
    
    return {
      token,
      refreshToken: `refresh-${token}`
    };
  }

  static async getCurrentUser(token: string): Promise<User> {
    await new Promise(resolve => setTimeout(resolve, 200));
    
    // Extract user ID from mock token
    const userId = token.includes('mock-jwt-token-1') ? '1' : '2';
    const user = MockAuthAPI.MOCK_USERS.find(u => u.id === userId);
    
    if (!user) {
      throw new Error('User not found');
    }
    
    return user;
  }
}

// Environment-based API selection
const isDevelopment = import.meta.env?.DEV ?? true;
export const authAPI = isDevelopment ? MockAuthAPI : AuthAPI;