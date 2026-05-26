
document.addEventListener('DOMContentLoaded', function() {
    const customerSelect = document.querySelector('#id_customer');
    const phoneInput = document.querySelector('#id_phone_number');
    const passwordInput = document.querySelector('#id_password_hash');

    if (customerSelect) {
        customerSelect.addEventListener('change', function() {
            const customerId = this.value;

            if (customerId) {
                // Fetch customer data from API
                fetch(`/api/customer/${customerId}/`)
                    .then(response => response.json())
                    .then(data => {
                        if (phoneInput) {
                            phoneInput.value = data.phone || '';
                        }
                        // Password will be set to 123456789 automatically on save
                    })
                    .catch(error => console.error('Error fetching customer data:', error));
            }
        });
    }
});
