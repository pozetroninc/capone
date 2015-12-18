# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ledger', '0002_auto_20151211_1501'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='ledger',
            name='are_debits_positive',
        ),
        migrations.AddField(
            model_name='ledger',
            name='increased_by_debits',
            field=models.BooleanField(default=True, help_text=b'All accounts (and their corresponding ledgers) are of one of two types: either debits increase the value of an account or credits do.  By convention, asset and expense accounts are of the former type, while liabilities, equity, and revenue are of the latter.'),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='transaction',
            name='type',
            field=models.CharField(default=b'Manual', max_length=128, verbose_name='The type of ledger', choices=[(b'Automatic', b'Automatic'), (b'Manual', b'Manual'), (b'Reconciliation', b'Reconciliation')]),
        ),
        migrations.AlterField(
            model_name='ledgerentry',
            name='amount',
            field=models.DecimalField(verbose_name='Amount of this entry.', max_digits=24, decimal_places=4),
        ),
    ]
