import frappe
from dateutil import relativedelta
from frappe.utils import getdate, cint
from erpnext.accounts.doctype.subscription.subscription import get_prorata_factor
from erpnext.accounts.doctype.accounting_dimension.accounting_dimension import get_accounting_dimensions
from erpnext.accounts.doctype.subscription_plan.subscription_plan import get_prorate_factor
from erpnext.utilities.product import get_price
from erpnext.accounts.doctype.subscription.subscription import Subscription

class CustomSubscription(Subscription):
	def get_items_from_plans(self, plans: list[dict[str, str]], prorate: bool | None = None) -> list[dict]:
		"""
		Returns the `Item`s linked to `Subscription Plan`
		"""
		if prorate is None:
			prorate = False

		if prorate:
			prorate_factor = get_prorata_factor(
				self.current_invoice_end,
				self.current_invoice_start,
				cint(self.generate_invoice_at == "Beginning of the current subscription period"),
			)

		items = []
		party = self.party
		for plan in plans:
			plan_doc = frappe.get_doc("Subscription Plan", plan.plan)

			item_code = plan_doc.item

			if self.party == "Customer":
				deferred_field = "enable_deferred_revenue"
			else:
				deferred_field = "enable_deferred_expense"

			deferred = frappe.db.get_value("Item", item_code, deferred_field)

			if not prorate:
				item = {
					"item_code": item_code,
					"qty": plan.qty,
					"rate": get_plan_rate(
						plan.plan,
						plan.qty,
						party,
						self.current_invoice_start,
						self.current_invoice_end,
					),
					"cost_center": plan_doc.cost_center,
				}
			else:
				item = {
					"item_code": item_code,
					"qty": plan.qty,
					"rate": get_plan_rate(
						plan.plan,
						plan.qty,
						party,
						self.current_invoice_start,
						self.current_invoice_end,
						prorate_factor,
					),
					"cost_center": plan_doc.cost_center,
				}

			if deferred:
				item.update(
					{
						deferred_field: deferred,
						"service_start_date": self.current_invoice_start,
						"service_end_date": self.current_invoice_end,
					}
				)

			accounting_dimensions = get_accounting_dimensions()

			for dimension in accounting_dimensions:
				if plan_doc.get(dimension):
					item.update({dimension: plan_doc.get(dimension)})

			items.append(item)

		return items

@frappe.whitelist()
def get_plan_rate(
	plan, quantity=1, customer=None, start_date=None, end_date=None, prorate_factor=1, party=None
):
	plan = frappe.get_doc("Subscription Plan", plan)
	if plan.price_determination == "Fixed Rate":
		return plan.cost * prorate_factor

	elif plan.price_determination == "Based On Price List":
		if customer:
			customer_group = frappe.db.get_value("Customer", customer, "customer_group")
		else:
			customer_group = None

		price = get_price(
			item_code=plan.item,
			price_list=plan.price_list,
			customer_group=customer_group,
			company=None,
			qty=quantity,
			party=party,
		)
		if not price:
			return 0
		else:
			return price.price_list_rate * prorate_factor

	elif plan.price_determination == "Monthly Rate":
		start_date = getdate(start_date)
		end_date = getdate(end_date)

		no_of_months = relativedelta.relativedelta(end_date, start_date).months + 1
		cost = plan.cost * no_of_months

		# Adjust cost if start or end date is not month start or end
		prorate = frappe.db.get_single_value("Subscription Settings", "prorate")

		if prorate:
			cost -= plan.cost * get_prorate_factor(start_date, end_date)
		return cost
	
	elif plan.price_determination == "Daily Rate":
		start_date = getdate(start_date)
		end_date = getdate(end_date)
		
		no_of_days = (end_date - start_date).days + 1
		cost = plan.cost * no_of_days
		
		prorate = frappe.db.get_single_value("Subscription Settings", "prorate")
		
		if prorate:
			cost -= plan.cost * get_prorate_factor(start_date, end_date)
		
		return cost