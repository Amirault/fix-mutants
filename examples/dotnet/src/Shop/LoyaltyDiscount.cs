namespace Shop;

public static class LoyaltyDiscount
{
    public static decimal Apply(decimal price, int yearsAsCustomer)
    {
        if (yearsAsCustomer >= 5)
        {
            return price * 0.90m;
        }

        if (yearsAsCustomer >= 2)
        {
            return price * 0.95m;
        }

        return price;
    }
}
