// Function to get a cookie value by name
function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) {
        return parts.pop().split(';').shift();
    }
    return null;
}

function loadUserData() {
    const userId = getCookie('user_session');
    const userDataDiv = document.getElementById('user-data');

    if (userId) {
        fetch(`/get_user_json`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({user_id: userId})
        })
            .then(response => {
                if (!response.ok) {
                    throw new Error(`Error fetching user data: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                userDataDiv.innerHTML = `
                    <h2>User Information</h2>
                    <p><strong>Name:</strong> ${data.name}</p>
                    <p><strong>Karma:</strong> ${data.karma}</p>
                    <p><strong>Socials:</strong> ${data.socials.join(', ')}</p>
                `;
            })
            .catch(error => {
                console.error('Error:', error);
                userDataDiv.innerHTML = '<p>Failed to load user data.</p>';
            });
    } else {
        userDataDiv.innerHTML = '<p>No user session found. Please log in.</p>';
    }
}

// Call the function to load user data
document.addEventListener('DOMContentLoaded', loadUserData);