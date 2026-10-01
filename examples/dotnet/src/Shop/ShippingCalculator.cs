namespace Shop;

public static class ShippingCalculator
{
    private const decimal FreeShippingThreshold = 100m;
    private const decimal StandardRate = 4.90m;
    private const decimal HeavyParcelSurcharge = 7.50m;
    private const decimal HeavyParcelKilograms = 20m;

    public static decimal Calculate(decimal orderTotal, decimal weightInKilograms)
    {
        if (orderTotal < 0)
        {
            throw new ArgumentOutOfRangeException(nameof(orderTotal));
        }

        if (orderTotal >= FreeShippingThreshold)
        {
            return 0m;
        }

        var cost = StandardRate;
        if (weightInKilograms > HeavyParcelKilograms)
        {
            cost += HeavyParcelSurcharge;
        }

        return cost;
    }
}
