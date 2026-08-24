"""
Tests for restocking API endpoints.
"""
import pytest

import main


@pytest.fixture(autouse=True)
def reset_submitted_orders():
    """
    Clear submitted restock orders before each test.

    The endpoint appends to a module-level list, so without this every POST
    would leak into later tests and the generated order numbers would shift.
    """
    main.submitted_restock_orders.clear()
    yield
    main.submitted_restock_orders.clear()


@pytest.fixture
def sample_restock_items():
    """Two valid restock line items with differing lead times."""
    return [
        {
            "item_sku": "WDG-001",
            "item_name": "Industrial Widget Type A",
            "quantity": 150,
            "unit_cost": 45.0,
            "lead_time_days": 14,
            "line_total": 6750.0,
        },
        {
            "item_sku": "GSK-203",
            "item_name": "High-Temperature Gasket",
            "quantity": 100,
            "unit_cost": 12.75,
            "lead_time_days": 10,
            "line_total": 1275.0,
        },
    ]


class TestDemandForecastSupplyFields:
    """Test suite for the supply fields the Restocking tab depends on."""

    def test_demand_forecasts_include_supply_fields(self, client):
        """Test that every forecast carries unit_cost and lead_time_days."""
        response = client.get("/api/demand")
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0

        for forecast in data:
            assert "unit_cost" in forecast
            assert "lead_time_days" in forecast

    def test_demand_forecast_supply_field_types(self, client):
        """Test that supply fields are proper numeric types."""
        response = client.get("/api/demand")
        data = response.json()

        for forecast in data:
            assert isinstance(forecast["unit_cost"], (int, float))
            assert isinstance(forecast["lead_time_days"], int)
            assert forecast["unit_cost"] > 0
            assert forecast["lead_time_days"] > 0

    def test_demand_forecast_cost_matches_inventory(self, client):
        """Test that a SKU present in both fixtures is priced consistently."""
        demand = client.get("/api/demand").json()
        inventory = client.get("/api/inventory").json()

        inventory_costs = {item["sku"]: item["unit_cost"] for item in inventory}
        overlapping = [f for f in demand if f["item_sku"] in inventory_costs]

        # PSU-501 is currently the only SKU in both fixtures. If the fixtures
        # are ever reconciled this loop simply covers more of them.
        assert len(overlapping) > 0

        for forecast in overlapping:
            expected = inventory_costs[forecast["item_sku"]]
            assert abs(forecast["unit_cost"] - expected) < 0.01


class TestRestockOrderEndpoints:
    """Test suite for restock order creation and retrieval."""

    def test_get_restock_orders_empty(self, client):
        """Test that no orders are returned before any are submitted."""
        response = client.get("/api/restock-orders")
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0

    def test_create_restock_order(self, client, sample_restock_items):
        """Test submitting a valid restocking order."""
        response = client.post(
            "/api/restock-orders",
            json={"budget": 50000, "items": sample_restock_items},
        )
        assert response.status_code == 201

        order = response.json()
        assert order["id"] == "1"
        assert order["order_number"].startswith("RST-")
        assert order["status"] == "Submitted"
        assert len(order["items"]) == 2

    def test_create_restock_order_total_value(self, client, sample_restock_items):
        """Test that total value is the sum of the line totals."""
        response = client.post(
            "/api/restock-orders",
            json={"budget": 50000, "items": sample_restock_items},
        )
        order = response.json()

        expected = sum(item["line_total"] for item in sample_restock_items)
        assert abs(order["total_value"] - expected) < 0.01

    def test_create_restock_order_lead_time_is_slowest_item(
        self, client, sample_restock_items
    ):
        """Test that order lead time is the max across items, not the sum."""
        response = client.post(
            "/api/restock-orders",
            json={"budget": 50000, "items": sample_restock_items},
        )
        order = response.json()

        expected = max(item["lead_time_days"] for item in sample_restock_items)
        assert order["lead_time_days"] == expected
        assert order["lead_time_days"] == 14

    def test_create_restock_order_expected_delivery(
        self, client, sample_restock_items
    ):
        """Test that expected delivery is submitted date plus lead time."""
        from datetime import datetime, timedelta

        response = client.post(
            "/api/restock-orders",
            json={"budget": 50000, "items": sample_restock_items},
        )
        order = response.json()

        submitted = datetime.fromisoformat(order["submitted_date"])
        delivery = datetime.fromisoformat(order["expected_delivery"])
        assert delivery == submitted + timedelta(days=order["lead_time_days"])

    def test_create_restock_order_preserves_budget(
        self, client, sample_restock_items
    ):
        """Test that the budget the order was built against is recorded."""
        response = client.post(
            "/api/restock-orders",
            json={"budget": 37500, "items": sample_restock_items},
        )
        order = response.json()

        assert order["budget"] == 37500

    def test_create_restock_order_rejects_empty_items(self, client):
        """Test that an order with no items is rejected."""
        response = client.post(
            "/api/restock-orders", json={"budget": 5000, "items": []}
        )
        assert response.status_code == 400

        data = response.json()
        assert "detail" in data
        assert "at least one item" in data["detail"].lower()

    def test_create_restock_order_rejects_over_budget(
        self, client, sample_restock_items
    ):
        """Test that an order exceeding its budget is rejected."""
        response = client.post(
            "/api/restock-orders",
            json={"budget": 100, "items": sample_restock_items},
        )
        assert response.status_code == 400

        data = response.json()
        assert "detail" in data
        assert "exceeds budget" in data["detail"].lower()

    def test_create_restock_order_allows_exact_budget(self, client):
        """Test that an order totalling exactly the budget is accepted."""
        items = [
            {
                "item_sku": "GSK-203",
                "item_name": "High-Temperature Gasket",
                "quantity": 100,
                "unit_cost": 12.75,
                "lead_time_days": 10,
                "line_total": 1275.0,
            }
        ]
        response = client.post(
            "/api/restock-orders", json={"budget": 1275.0, "items": items}
        )
        assert response.status_code == 201

    def test_create_restock_order_rejects_malformed_item(self, client):
        """Test that a line item missing required fields is rejected."""
        response = client.post(
            "/api/restock-orders",
            json={"budget": 5000, "items": [{"item_sku": "WDG-001"}]},
        )
        assert response.status_code == 422

    def test_submitted_order_appears_in_list(self, client, sample_restock_items):
        """Test that a submitted order is returned by the GET endpoint."""
        create_response = client.post(
            "/api/restock-orders",
            json={"budget": 50000, "items": sample_restock_items},
        )
        created = create_response.json()

        response = client.get("/api/restock-orders")
        assert response.status_code == 200

        data = response.json()
        assert len(data) == 1
        assert data[0]["order_number"] == created["order_number"]

    def test_restock_orders_returned_newest_first(
        self, client, sample_restock_items
    ):
        """Test that the list is ordered newest first."""
        first = client.post(
            "/api/restock-orders",
            json={"budget": 50000, "items": sample_restock_items},
        ).json()
        second = client.post(
            "/api/restock-orders",
            json={"budget": 50000, "items": sample_restock_items},
        ).json()

        data = client.get("/api/restock-orders").json()
        assert len(data) == 2
        assert data[0]["order_number"] == second["order_number"]
        assert data[1]["order_number"] == first["order_number"]

    def test_restock_order_numbers_are_sequential(
        self, client, sample_restock_items
    ):
        """Test that order numbers increment across submissions."""
        numbers = []
        for _ in range(3):
            response = client.post(
                "/api/restock-orders",
                json={"budget": 50000, "items": sample_restock_items},
            )
            numbers.append(response.json()["order_number"])

        suffixes = [int(number.split("-")[-1]) for number in numbers]
        assert suffixes == [1, 2, 3]

    def test_restock_order_item_structure(self, client, sample_restock_items):
        """Test that returned line items keep their full structure."""
        response = client.post(
            "/api/restock-orders",
            json={"budget": 50000, "items": sample_restock_items},
        )
        order = response.json()

        for item in order["items"]:
            assert "item_sku" in item
            assert "item_name" in item
            assert "quantity" in item
            assert "unit_cost" in item
            assert "lead_time_days" in item
            assert "line_total" in item
            assert isinstance(item["quantity"], int)
            assert isinstance(item["unit_cost"], (int, float))
            assert isinstance(item["lead_time_days"], int)

    def test_restock_orders_do_not_affect_customer_orders(
        self, client, sample_restock_items
    ):
        """Test that submitting a restock order leaves /api/orders untouched."""
        before = len(client.get("/api/orders").json())

        client.post(
            "/api/restock-orders",
            json={"budget": 50000, "items": sample_restock_items},
        )

        after = len(client.get("/api/orders").json())
        assert after == before
