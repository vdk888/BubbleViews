'use client';

import { useRouter } from 'next/navigation';
import { apiClient } from '@/lib/api-client';

const PERSONA_STORAGE_KEY = "selected_persona_id";

export function LogoutButton() {
  const router = useRouter();

  const handleLogout = () => {
    apiClient.clearToken();
    // Clear stored persona selection on logout
    localStorage.removeItem(PERSONA_STORAGE_KEY);
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
