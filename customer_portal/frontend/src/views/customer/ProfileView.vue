<script setup>
import { ref, onMounted } from 'vue';
import { getProfile } from '../../api/customer';
import LoadingSpinner from '../../components/ui/LoadingSpinner.vue';

const loading = ref(true);
const customer = ref(null);

function fmtDate(d) {
  return new Date(d).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
}

onMounted(async () => {
  const data = await getProfile();
  customer.value = data.customer;
  loading.value = false;
});
</script>

<template>
  <div>
    <div class="mb-8">
      <h1 class="text-3xl font-bold text-gray-800 mb-2">
        <i class="fas fa-user mr-3 text-primary-600"></i>My Profile
      </h1>
      <p class="text-gray-600">View and manage your account information</p>
    </div>

    <LoadingSpinner v-if="loading" />

    <div v-else-if="customer" class="grid grid-cols-1 lg:grid-cols-3 gap-8">
      <div class="lg:col-span-1">
        <div class="bg-white rounded-xl p-6 card-shadow">
          <div class="text-center">
            <div class="w-24 h-24 rounded-full bg-gradient-to-br from-primary-500 to-primary-600 flex items-center justify-center mx-auto mb-4">
              <i class="fas fa-user text-4xl text-white"></i>
            </div>
            <h4 class="text-xl font-bold text-gray-800 mb-1">{{ customer.name }}</h4>
            <p class="text-gray-500">
              <span
                class="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium"
                :class="customer.type === 'DEALER' ? 'bg-primary-100 text-primary-800' : 'bg-blue-100 text-blue-800'"
              >{{ customer.type === 'DEALER' ? 'Dealer Account' : 'Individual Account' }}</span>
            </p>
          </div>
        </div>
      </div>

      <div class="lg:col-span-2 space-y-6">
        <div class="bg-white rounded-xl p-6 card-shadow">
          <h5 class="text-lg font-semibold text-gray-800 mb-4 flex items-center">
            <i class="fas fa-id-card mr-3 text-blue-500"></i>Personal Information
          </h5>
          <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <label class="text-sm text-gray-500 block mb-1">Full Name</label>
              <p class="text-gray-800 font-semibold">{{ customer.name }}</p>
            </div>
            <div v-if="customer.father_name">
              <label class="text-sm text-gray-500 block mb-1">Father's Name</label>
              <p class="text-gray-800">{{ customer.father_name }}</p>
            </div>
            <div v-if="customer.cnic">
              <label class="text-sm text-gray-500 block mb-1">CNIC Number</label>
              <p class="text-gray-800 font-mono">{{ customer.cnic }}</p>
            </div>
            <div v-if="customer.phone">
              <label class="text-sm text-gray-500 block mb-1">Phone Number</label>
              <p class="text-gray-800">{{ customer.phone }}</p>
            </div>
          </div>
        </div>

        <div v-if="customer.type === 'DEALER'" class="bg-white rounded-xl p-6 card-shadow">
          <h5 class="text-lg font-semibold text-gray-800 mb-4 flex items-center">
            <i class="fas fa-building mr-3 text-gray-500"></i>Business Information
          </h5>
          <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div v-if="customer.business_name">
              <label class="text-sm text-gray-500 block mb-1">Business Name</label>
              <p class="text-gray-800 font-semibold">{{ customer.business_name }}</p>
            </div>
            <div v-if="customer.ntn">
              <label class="text-sm text-gray-500 block mb-1">NTN Number</label>
              <p class="text-gray-800 font-mono">{{ customer.ntn }}</p>
            </div>
          </div>
        </div>

        <div class="bg-white rounded-xl p-6 card-shadow">
          <h5 class="text-lg font-semibold text-gray-800 mb-4 flex items-center">
            <i class="fas fa-map-marker-alt mr-3 text-yellow-500"></i>Address
          </h5>
          <p v-if="customer.address" class="text-gray-800">{{ customer.address }}</p>
          <p v-else class="text-gray-400">No address on file</p>
        </div>

        <div class="bg-white rounded-xl p-6 card-shadow">
          <h5 class="text-lg font-semibold text-gray-800 mb-4 flex items-center">
            <i class="fas fa-info-circle mr-3 text-gray-500"></i>Account Details
          </h5>
          <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div class="bg-gray-50 rounded-lg p-4">
              <label class="text-sm text-gray-500 block mb-1">Account Created</label>
              <h5 class="text-gray-800 font-semibold">{{ fmtDate(customer.created_at) }}</h5>
            </div>
            <div class="bg-gray-50 rounded-lg p-4">
              <label class="text-sm text-gray-500 block mb-1">Account Status</label>
              <h5 class="text-gray-800 font-semibold"><span class="text-green-600">Active</span></h5>
            </div>
          </div>
        </div>

        <div class="bg-blue-50 border border-blue-200 rounded-xl p-6">
          <h5 class="text-lg font-semibold text-blue-800 mb-3 flex items-center">
            <i class="fas fa-shield-alt mr-3"></i>Security
          </h5>
          <p class="text-blue-700">
            <i class="fas fa-info-circle mr-2"></i>
            For security reasons, password changes must be requested through administration.
          </p>
        </div>
      </div>
    </div>
  </div>
</template>
