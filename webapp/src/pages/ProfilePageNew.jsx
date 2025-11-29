import React from 'react';
import BottomNav from '../components/BottomNav';
import './ProfilePageNew.css';

const getStoredUser = () => {
  if (typeof window === 'undefined') {
    return null;
  }

  try {
    const raw = localStorage.getItem('fudly_user');
    return raw ? JSON.parse(raw) : null;
  } catch (error) {
    console.error('Failed to parse stored user:', error);
    return null;
  }
};

const ProfilePage = ({ onNavigate, user }) => {
  const storedUser = getStoredUser();
  const profile = storedUser || user || {};
  const userName = profile.first_name
    ? `${profile.first_name}${profile.last_name ? ` ${profile.last_name}` : ''}`
    : 'Foydalanuvchi';
  const userEmail = profile.username
    ? `@${profile.username}`
    : profile.phone || 'user@example.com';
  const avatarUrl = profile.photo_url
    ? profile.photo_url
    : `https://ui-avatars.com/api/?name=${encodeURIComponent(userName)}`;

  const menuItems = [
    { icon: '📦', label: 'Orders', hasNew: false },
    { icon: '👤', label: 'My Details', hasNew: false },
    { icon: '📍', label: 'Delivery Address', hasNew: false },
    { icon: '💳', label: 'Payment Methods', hasNew: false },
    { icon: '🎟️', label: 'Promo Cord', hasNew: false },
    { icon: '🔔', label: 'Notifications', hasNew: false },
    { icon: '❓', label: 'Help', hasNew: false },
    { icon: 'ℹ️', label: 'About', hasNew: false },
  ];

  const handleMenuClick = (label) => {
    switch(label) {
      case 'Orders':
        alert('Buyurtmalar sahifasi ishlab chiqilmoqda...');
        break;
      case 'My Details':
        alert('Shaxsiy ma\'lumotlar tahrirlash tez orada...');
        break;
      case 'Delivery Address':
        alert('Yetkazish manzili tez orada...');
        break;
      case 'Payment Methods':
        alert('To\'lov usullari tez orada...');
        break;
      case 'Promo Cord':
        alert('Promokod tez orada...');
        break;
      case 'Notifications':
        alert('Bildirishnomalar sozlamalari tez orada...');
        break;
      case 'Help':
        alert('Yordam bo\'limi tez orada...');
        break;
      case 'About':
        alert('Fudly - yaqin atrofdagi yangi mahsulotlarni toping!\n\nVersiya 1.0.0');
        break;
    }
  };

  const handleLogout = () => {
    if (confirm('Akkauntdan chiqmoqchimisiz?')) {
      localStorage.clear();
      if (onNavigate) {
        onNavigate('home');
      } else {
        window.location.href = '/';
      }
    }
  };

  return (
    <div className="profile-page">
      <div className="profile-user-section">
        <div className="profile-user-avatar">
          <img
            src={avatarUrl}
            alt={userName}
          />
        </div>
        <div className="profile-user-info">
          <div className="profile-user-name">{userName}</div>
          <div className="profile-user-email">{userEmail}</div>
        </div>
        <button className="profile-edit-btn">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
            <path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04c.39-.39.39-1.02 0-1.41l-2.34-2.34c-.39-.39-1.02-.39-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z" fill="#53B175"/>
          </svg>
        </button>
      </div>

      <div className="profile-menu">
        {menuItems.map((item, index) => (
          <button key={index} className="profile-menu-item" onClick={() => handleMenuClick(item.label)}>
            <span className="menu-item-icon">{item.icon}</span>
            <span className="menu-item-label">{item.label}</span>
            <svg className="menu-item-arrow" width="8" height="14" viewBox="0 0 8 14" fill="none">
              <path d="M1 13L7 7L1 1" stroke="#181725" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </button>
        ))}
      </div>

      <button className="profile-logout-btn" onClick={handleLogout}>
        <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
          <path d="M13.3333 14.1667L17.5 10M17.5 10L13.3333 5.83333M17.5 10H7.5M7.5 17.5H4.16667C3.24619 17.5 2.5 16.7538 2.5 15.8333V4.16667C2.5 3.24619 3.24619 2.5 4.16667 2.5H7.5" stroke="#53B175" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
        Log Out
      </button>

      <BottomNav currentPage="profile" onNavigate={onNavigate} />
    </div>
  );
};

export default ProfilePage;
