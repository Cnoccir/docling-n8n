import { formatDistanceToNow, format as formatDate } from 'date-fns';

export function formatFileSize(bytes: number): string {
  if (bytes === 0) return '0 Bytes';

  const k = 1024;
  const sizes = ['Bytes', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));

  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`;
}

export function formatCurrency(amount: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 4,
  }).format(amount);
}

export function formatNumber(num: number): string {
  return new Intl.NumberFormat('en-US').format(num);
}

export function formatDuration(seconds: number | null): string {
  if (seconds === null || seconds === 0) return '0s';

  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = Math.floor(seconds % 60);

  const parts: string[] = [];
  if (hours > 0) parts.push(`${hours}h`);
  if (minutes > 0) parts.push(`${minutes}m`);
  if (secs > 0 || parts.length === 0) parts.push(`${secs}s`);

  return parts.join(' ');
}

export function formatRelativeTime(dateString: string | null): string {
  if (!dateString) return 'N/A';
  
  try {
    const date = new Date(dateString);
    return formatDistanceToNow(date, { addSuffix: true });
  } catch {
    return 'Invalid date';
  }
}

export function formatDateTime(dateString: string | null): string {
  if (!dateString) return 'N/A';
  
  try {
    const date = new Date(dateString);
    return formatDate(date, 'MMM dd, yyyy HH:mm:ss');
  } catch {
    return 'Invalid date';
  }
}

export function formatPercentage(value: number, decimals = 0): string {
  return `${value.toFixed(decimals)}%`;
}

export function truncate(str: string, maxLength: number): string {
  if (str.length <= maxLength) return str;
  return str.slice(0, maxLength - 3) + '...';
}

export function getStatusColor(status: string): string {
  const colors: Record<string, string> = {
    queued: 'gray',
    processing: 'blue',
    completed: 'green',
    failed: 'red',
    cancelled: 'yellow',
  };
  return colors[status.toLowerCase()] || 'gray';
}

export function getStatusBadgeClass(status: string): string {
  const classes: Record<string, string> = {
    queued: 'badge badge-gray',
    processing: 'badge badge-info',
    completed: 'badge badge-success',
    failed: 'badge badge-error',
    cancelled: 'badge badge-warning',
  };
  return classes[status.toLowerCase()] || 'badge badge-gray';
}
