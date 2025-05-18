function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) {
        return parts.pop().split(';').shift();
    }
    return null;
}

async function loadUserData() {
    const userId = getCookie('user_session');

    if (userId) {
        try {
            const response = await fetch(`/get_user_json`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({user_id: userId})
            });

            if (!response.ok) {
                throw new Error(`Error fetching user data: ${response.status}`);
            }

            return response.json();
        } catch (error) {
            console.error('Error:', error);
            return null;
        }
    } else {
        console.error('No user session found. Please log in.');
        return null;
    }
}