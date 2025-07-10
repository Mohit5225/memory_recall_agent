import React from 'react';
import '../styles/colors.css';
import styles from './Dashboard.module.css';

const Dashboard = () => {
    return (
        <div className={styles.dashboard}>
            <div className={styles.sidebar}>
                <input className={styles.searchInput} type="text" placeholder="Search..." />
                <button className={styles.sidebarButtonNewChat}>New Chat</button>
                {/* ...other sidebar elements... */}
            </div>
            <div className={styles.mainContent}>
                {/* ...main content elements... */}
            </div>
        </div>
    );
};

export default Dashboard;