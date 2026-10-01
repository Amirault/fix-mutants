const FREE_SHIPPING_THRESHOLD = 100;
const STANDARD_RATE = 4.9;
const HEAVY_PARCEL_SURCHARGE = 7.5;
const HEAVY_PARCEL_KILOGRAMS = 20;

function calculateShipping(orderTotal, weightInKilograms) {
  if (orderTotal < 0) {
    throw new RangeError("orderTotal must not be negative");
  }
  if (orderTotal >= FREE_SHIPPING_THRESHOLD) {
    return 0;
  }
  let cost = STANDARD_RATE;
  if (weightInKilograms > HEAVY_PARCEL_KILOGRAMS) {
    cost += HEAVY_PARCEL_SURCHARGE;
  }
  return cost;
}

module.exports = { calculateShipping };
