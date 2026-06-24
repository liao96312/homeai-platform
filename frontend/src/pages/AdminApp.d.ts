import type React from 'react';

type AdminAppProps = {
  onLogout: () => void;
};

declare const AdminApp: React.ComponentType<AdminAppProps>;
export default AdminApp;

