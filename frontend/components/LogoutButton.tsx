'use client';

import { useRouter } from 'next/navigation';
import { apiClient } from '@/lib/api-client';

export function LogoutButton() {
  const router = useRouter();

  const handleLogout = () => {
    apiClient.clearToken();
    router.push('/login');
  };

  return (
    <button
      onClick={handleLogout}
      className="soft-button text-sm"
      title="Sign out"
    >
      Sign Out
    </button>
  );
}
