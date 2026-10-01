const { calculateShipping } = require("../src/shipping");

describe("calculateShipping", () => {
  test("given a small light order, charges the standard rate", () => {
    expect(calculateShipping(50, 1)).toBe(4.9);
  });

  test("given a large order, ships for free", () => {
    expect(calculateShipping(250, 1)).toBe(0);
  });

  test("given a negative total, throws", () => {
    expect(() => calculateShipping(-1, 1)).toThrow(RangeError);
  });

  test("given a heavy parcel, adds the surcharge", () => {
    expect(calculateShipping(50, 30)).toBeCloseTo(12.4);
  });
});
