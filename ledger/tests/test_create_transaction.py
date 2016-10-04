import mock
from datetime import datetime
from decimal import Decimal as D

from django.test import TestCase

from ledger.exceptions import ExistingLedgerEntriesException
from ledger.exceptions import NoLedgerEntriesException
from ledger.exceptions import TransactionBalanceException
from ledger.models import LedgerEntry
from ledger.models import Transaction
from ledger.api.actions import create_transaction
from ledger.api.actions import credit
from ledger.api.actions import debit
from ledger.api.queries import get_balances_for_object
from ledger.api.queries import validate_transaction
from ledger.tests.factories import CreditCardTransactionFactory
from ledger.tests.factories import LedgerFactory
from ledger.tests.factories import OrderFactory
from ledger.tests.factories import TransactionTypeFactory
from ledger.tests.factories import UserFactory
from ledger.tests.models import CreditCardTransaction
from ledger.tests.models import Order


RECONCILIATION_TYPE_NAME = 'Recon'


def create_recon_report():
    """
    Return a report for all existing Orders showing their Recon status

    This report has one entry for each order and gives important information
    about that Order: ID, datetime created, the amount originally charged for
    it, and its barcode: its unique identifier in the lab.  Then the remaining
    three columns contain the ID, create datetime, and barcode for the
    CreditCardTransaction that is reconciled to it.

    This report is meant to mimic the one with the same columns we create in
    Looker to perform Revenue Recognition.
    """
    report = ""
    for transaction in Transaction.objects.filter(
            type__name=RECONCILIATION_TYPE_NAME):
        related_objects = {
            type(related_object.related_object): related_object.related_object
            for related_object in transaction.related_objects.all()
        }
        order = related_objects[Order]
        credit_card_transaction = related_objects[CreditCardTransaction]
        report += ",".join(map(str, [
            order.id,
            order.datetime,
            order.amount,
            order.barcode,
            credit_card_transaction.id,
            credit_card_transaction.datetime,
            credit_card_transaction.amount,
        ]))
        report += '\n'
    return report


class TestCompanyWideLedgers(TestCase):
    def setUp(self):
        self.AMOUNT = D(100)
        self.user = UserFactory()

        self.accounts_receivable = LedgerFactory(name='Accounts Receivable')
        self.cash_unrecon = LedgerFactory(name='Cash (unreconciled)')
        self.cash_recon = LedgerFactory(name='Cash (reconciled)')
        self.revenue = LedgerFactory(name='Revenue', increased_by_debits=False)
        self.recon_ttype = TransactionTypeFactory(
            name=RECONCILIATION_TYPE_NAME)

    def test_using_company_wide_ledgers_for_reconciliation(self):
        """
        Test ledger behavior with a Recon and Recog proof-of-principle

        This test creates an Order and a CreditCardTransaction and using the
        four Ledgers created in setUp, it makes all of the ledger entries that
        an Order and Transaction would be expected to have.  There are three,
        specifically: Revenue Recognition (CR: Revenue, DR:A/R), recording
        incoming cash (CR: A/R, DR: Cash (unreconciled)) and Reconciliation
        (CR: Cash (reconciled), DR: Cash (unreconciled)).

        In table form:

        Event                   | Accounts Receivable (unreconciled) | Revenue | Cash (unreconciled) | Cash (reconciled) | Evidence Models
        ----------------------- | ---------------------------------- | ------- | ------------------- | ----------------- | --------------------------------------------------------------
        Test is complete        | -$500                              | +$500   |                     |                   | `Order`
        Patient pays            | +$500                              |         | -$500               |                   | `CreditCardTransaction`
        Payments are reconciled |                                    |         | +$500               | -$500             | both `Order` and `CreditCardTransaction`
        """  # nopep8
        order = OrderFactory()
        credit_card_transaction = CreditCardTransactionFactory()

        # Assert that this Order looks "unrecognized".
        self.assertEqual(
            get_balances_for_object(order),
            {},
        )

        # Add an entry debiting AR and crediting Revenue: this entry should
        # reference the Order.
        create_transaction(
            self.user,
            evidence=[order],
            ledger_entries=[
                LedgerEntry(
                    ledger=self.revenue,
                    amount=credit(self.AMOUNT)),
                LedgerEntry(
                    ledger=self.accounts_receivable,
                    amount=debit(self.AMOUNT)),
            ],
        )

        # Assert that the correct entries were created.
        self.assertEqual(LedgerEntry.objects.count(), 2)
        self.assertEqual(Transaction.objects.count(), 1)

        # Assert that this Order looks "recognized".
        self.assertEqual(
            get_balances_for_object(order),
            {
                self.revenue: -self.AMOUNT,
                self.accounts_receivable: self.AMOUNT,
            },
        )

        # Add an entry crediting "A/R" and debiting "Cash (unreconciled)": this
        # entry should reference the CreditCardTransaction.
        create_transaction(
            self.user,
            evidence=[credit_card_transaction],
            ledger_entries=[
                LedgerEntry(
                    ledger=self.accounts_receivable,
                    amount=credit(self.AMOUNT)),
                LedgerEntry(
                    ledger=self.cash_unrecon,
                    amount=debit(self.AMOUNT))
            ],
        )

        # Assert that the correct entries were created
        self.assertEqual(LedgerEntry.objects.count(), 4)
        self.assertEqual(Transaction.objects.count(), 2)

        # Assert the CreditCardTransaction is in "Cash (unreconciled)".
        self.assertEqual(
            get_balances_for_object(credit_card_transaction),
            {
                self.accounts_receivable: -self.AMOUNT,
                self.cash_unrecon: self.AMOUNT,
            },
        )

        # Add an entry crediting "Cash (Unreconciled)" and debiting "Cash
        # (Reconciled)": this entry should reference both an Order and
        # a CreditCardTransaction.
        create_transaction(
            self.user,
            evidence=[order, credit_card_transaction],
            ledger_entries=[
                LedgerEntry(
                    ledger=self.cash_unrecon,
                    amount=credit(self.AMOUNT)),
                LedgerEntry(
                    ledger=self.cash_recon,
                    amount=debit(self.AMOUNT))
            ],
            type=self.recon_ttype,
        )

        # Assert that the correct entries were created.
        self.assertEqual(LedgerEntry.objects.count(), 6)
        self.assertEqual(Transaction.objects.count(), 3)

        # Assert that revenue is recognized and reconciled.
        self.assertEqual(
            get_balances_for_object(order),
            {
                self.accounts_receivable: self.AMOUNT,
                self.cash_unrecon: -self.AMOUNT,
                self.cash_recon: self.AMOUNT,
                self.revenue: -self.AMOUNT,
            },
        )

    def test_creating_demo_reconciliation_report(self):
        """
        Create a Reconciliation Report like the one we need in Website.

        See `create_recon_report` for more details.
        """
        new_now = datetime(2015, 12, 16, 12, 0, 0, 0)
        order1 = OrderFactory(amount=self.AMOUNT)
        order2 = OrderFactory(amount=self.AMOUNT)
        credit_card_transaction1 = CreditCardTransactionFactory(
            amount=self.AMOUNT)
        credit_card_transaction2 = CreditCardTransactionFactory(
            amount=self.AMOUNT)
        order1.datetime = new_now
        order1.save()
        order2.datetime = new_now
        order2.save()
        credit_card_transaction1.datetime = new_now
        credit_card_transaction1.save()
        credit_card_transaction2.datetime = new_now
        credit_card_transaction2.save()

        CASES = [
            (order1, credit_card_transaction1),
            (order2, credit_card_transaction2),
        ]

        for order, credit_card_transaction in CASES:
            create_transaction(
                self.user,
                evidence=[order],
                ledger_entries=[
                    LedgerEntry(
                        ledger=self.revenue,
                        amount=credit(self.AMOUNT)),
                    LedgerEntry(
                        ledger=self.accounts_receivable,
                        amount=debit(self.AMOUNT)),
                ],
            )

            create_transaction(
                self.user,
                evidence=[credit_card_transaction],
                ledger_entries=[
                    LedgerEntry(
                        ledger=self.accounts_receivable,
                        amount=credit(self.AMOUNT)),
                    LedgerEntry(
                        ledger=self.cash_unrecon,
                        amount=debit(self.AMOUNT))
                ],
            )

            create_transaction(
                self.user,
                evidence=[order, credit_card_transaction],
                ledger_entries=[
                    LedgerEntry(
                        ledger=self.cash_unrecon,
                        amount=credit(self.AMOUNT)),
                    LedgerEntry(
                        ledger=self.cash_recon,
                        amount=debit(self.AMOUNT))
                ],
                type=self.recon_ttype,
            )

            self.assertEqual(
                get_balances_for_object(order),
                {
                    self.accounts_receivable: self.AMOUNT,
                    self.cash_unrecon: -self.AMOUNT,
                    self.cash_recon: self.AMOUNT,
                    self.revenue: -self.AMOUNT,
                },
            )

        self.assertEqual(self.accounts_receivable.get_balance(), 0)
        self.assertEqual(self.cash_recon.get_balance(), self.AMOUNT * 2)
        self.assertEqual(self.cash_unrecon.get_balance(), 0)
        self.assertEqual(self.revenue.get_balance(), -self.AMOUNT * 2)

        self.assertEqual(
            create_recon_report(),
            "%s,2015-12-16 12:00:00,100.0000,%s,%s,2015-12-16 12:00:00,100.0000\n%s,2015-12-16 12:00:00,100.0000,%s,%s,2015-12-16 12:00:00,100.0000\n" %  # nopep8
            (
                order1.id,
                order1.barcode,
                credit_card_transaction1.id,
                order2.id,
                order2.barcode,
                credit_card_transaction2.id,
            ),
        )


class TestCreateTransaction(TestCompanyWideLedgers):
    def test_setting_posted_timestamp(self):
        POSTED_DATETIME = datetime(2016, 2, 7, 11, 59)
        order = OrderFactory(amount=self.AMOUNT)

        txn_recognize = create_transaction(
            self.user,
            evidence=[order],
            ledger_entries=[
                LedgerEntry(
                    ledger=self.revenue,
                    amount=credit(self.AMOUNT)),
                LedgerEntry(
                    ledger=self.accounts_receivable,
                    amount=debit(self.AMOUNT)),
            ],
            posted_timestamp=POSTED_DATETIME,
        )

        self.assertEqual(txn_recognize.posted_timestamp, POSTED_DATETIME)


class TestValidateTransaction(TestCompanyWideLedgers):
    def test_debits_not_equal_to_credits(self):
        with self.assertRaises(TransactionBalanceException):
            validate_transaction(
                self.user,
                ledger_entries=[
                    LedgerEntry(
                        ledger=self.revenue,
                        amount=credit(self.AMOUNT)),
                    LedgerEntry(
                        ledger=self.accounts_receivable,
                        amount=debit(self.AMOUNT + 2)),
                ],
            )

    def test_no_ledger_entries(self):
        with self.assertRaises(NoLedgerEntriesException):
            validate_transaction(
                self.user,
            )


class TestExistingLedgerEntriesException(TestCase):
    def setUp(self):
        self.amount = D(100)
        self.user = UserFactory()

        self.accounts_receivable = LedgerFactory(name='Accounts Receivable')
        self.cash = LedgerFactory(name='Cash')

    def test_with_existing_ledger_entry(self):
        existing_transaction = create_transaction(
            self.user,
            ledger_entries=[
                LedgerEntry(
                    ledger=self.accounts_receivable,
                    amount=credit(self.amount)),
                LedgerEntry(
                    ledger=self.accounts_receivable,
                    amount=debit(self.amount)),
            ],
        )

        with self.assertRaises(ExistingLedgerEntriesException):
            create_transaction(
                self.user,
                ledger_entries=list(existing_transaction.entries.all()),
            )


class TestCreditAndDebit(TestCase):
    """
    Test that `credit` and `debit` return the correctly signed amounts.
    """
    AMOUNT = D(100)

    def assertPositive(self, amount):
        self.assertGreaterEqual(amount, 0)

    def assertNegative(self, amount):
        self.assertLess(amount, 0)

    def test_credit_and_debit_helper_functions(self):
        with mock.patch('ledger.api.actions.settings') as mock_settings:
            mock_settings.DEBITS_ARE_NEGATIVE = True
            self.assertPositive(credit(self.AMOUNT))
            self.assertNegative(debit(self.AMOUNT))
        with mock.patch('ledger.api.actions.settings') as mock_settings:
            mock_settings.DEBITS_ARE_NEGATIVE = False
            self.assertNegative(credit(self.AMOUNT))
            self.assertPositive(debit(self.AMOUNT))

    def test_validation_error(self):
        self.assertRaises(ValueError, credit, -self.AMOUNT)
        self.assertRaises(ValueError, debit, -self.AMOUNT)


class TestRounding(TestCase):
    def _create_transaction_and_compare_to_amount(
            self, amount, comparison_amount=None):
        ledger1 = LedgerFactory()
        ledger2 = LedgerFactory()
        transaction = create_transaction(
            UserFactory(),
            ledger_entries=[
                LedgerEntry(
                    ledger=ledger1,
                    amount=amount),
                LedgerEntry(
                    ledger=ledger2,
                    amount=-amount),
            ]
        )

        entry1 = transaction.entries.get(ledger=ledger1)
        entry2 = transaction.entries.get(ledger=ledger2)
        if comparison_amount:
            self.assertNotEqual(entry1.amount, amount)
            self.assertEqual(entry1.amount, comparison_amount)
            self.assertNotEqual(entry2.amount, -amount)
            self.assertEqual(-entry2.amount, comparison_amount)
        else:
            self.assertEqual(entry1.amount, amount)
            self.assertEqual(entry2.amount, -amount)

    def test_precision(self):
        self._create_transaction_and_compare_to_amount(
            D('-499.9999'))

    def test_round_up(self):
        self._create_transaction_and_compare_to_amount(
            D('499.99995'), D('500'))

    def test_round_down(self):
        self._create_transaction_and_compare_to_amount(
            D('499.99994'), D('499.9999'))

    def test_round_up_negative(self):
        self._create_transaction_and_compare_to_amount(
            D('-499.99994'), D('-499.9999'))

    def test_round_down_negative(self):
        self._create_transaction_and_compare_to_amount(
            D('-499.99995'), D('-500'))
