const express = require('express');
const router = express.Router();

router.get('/api/config', (req, res) => {
  const clientConfig = {
    // Firebase config
    FIREBASE_API_KEY: process.env.FIREBASE_API_KEY,
    FIREBASE_AUTH_DOMAIN: process.env.FIREBASE_AUTH_DOMAIN,
    FIREBASE_PROJECT_ID: process.env.FIREBASE_PROJECT_ID,
    FIREBASE_STORAGE_BUCKET: process.env.FIREBASE_STORAGE_BUCKET,
    FIREBASE_MESSAGING_SENDER_ID: process.env.FIREBASE_MESSAGING_SENDER_ID,
    FIREBASE_APP_ID: process.env.FIREBASE_APP_ID,
    
    // Paystack config - using your existing variable name
    PAYSTACK_PUBLIC_KEY: process.env.paystackPublicKey,
    
    SERVICE_FEE: 50
  };
  
  res.json(clientConfig);
});

module.exports = router;