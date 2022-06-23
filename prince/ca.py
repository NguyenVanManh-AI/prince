"""Correspondence Analysis (CA)"""
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import sparse
from sklearn import base
from sklearn.utils import check_array

from prince import plot
from prince import utils
from prince import svd


class CA(base.BaseEstimator, base.TransformerMixin):
    def __init__(
        self,
        n_components=2,
        n_iter=10,
        copy=True,
        check_input=True,
        random_state=None,
        engine="sklearn",
    ):
        self.n_components = n_components
        self.n_iter = n_iter
        self.copy = copy
        self.check_input = check_input
        self.random_state = random_state
        self.engine = engine

    def fit(self, X, y=None):

        # Check input
        if self.check_input:
            check_array(X)

        # Check all values are positive
        if (X < 0).any().any():
            raise ValueError("All values in X should be positive")

        _, row_names, _, col_names = utils.make_labels_and_names(X)

        if isinstance(X, pd.DataFrame):
            X = X.to_numpy()

        if self.copy:
            X = np.copy(X)

        # Compute the correspondence matrix which contains the relative frequencies
        X = X.astype(float) / np.sum(X)

        # Compute row and column masses
        self.row_masses_ = pd.Series(X.sum(axis=1), index=row_names)
        self.col_masses_ = pd.Series(X.sum(axis=0), index=col_names)

        # Compute standardised residuals
        r = self.row_masses_.to_numpy()
        c = self.col_masses_.to_numpy()
        S = sparse.diags(r**-0.5) @ (X - np.outer(r, c)) @ sparse.diags(c**-0.5)
        # S = sparse.diags(1 / r**2) @ X @ sparse.diags(1 / c**2) - 1

        # Compute SVD on the standardised residuals
        self.svd_ = svd.compute_svd(
            X=S,
            n_components=self.n_components,
            n_iter=self.n_iter,
            random_state=self.random_state,
            engine=self.engine,
        )

        # Compute total inertia
        self.total_inertia_ = np.einsum("ij,ji->", S, S.T)

        return self

    def transform(self, X):
        """Computes the row principal coordinates of a dataset.

        Same as calling `row_coordinates`. In most cases you should be using the same
        dataset as you did when calling the `fit` method. You might however also want to included
        supplementary data.

        """
        if self.check_input:
            pass
            # utils.check_array(X)
        return self.row_coordinates(X)

    @property
    @utils.check_is_fitted
    def eigenvalues_(self):
        """Returns the eigenvalues associated with each principal component."""
        return np.square(self.svd_.s)

    @property
    @utils.check_is_fitted
    def percentage_of_variance_(self):
        """Returns the percentage of explained inertia per principal component."""
        return self.eigenvalues_ / self.total_inertia_

    @property
    @utils.check_is_fitted
    def cumulative_percentage_of_variance_(self):
        """Returns the percentage of explained inertia per principal component."""
        return np.cumsum(self.percentage_of_variance_)

    @property
    @utils.check_is_fitted
    def eigenvalues_summary(self):
        """Return a summary of the eigenvalues and their importance."""
        summary = pd.DataFrame(
            {
                "eigenvalue": self.eigenvalues_,
                r"% of variance": self.percentage_of_variance_,
                r"% of variance (cumulative)": self.cumulative_percentage_of_variance_,
            }
        ).style.format(
            {
                "eigenvalue": "{:,.3f}".format,
                "% of variance": "{:,.2%}".format,
                "% of variance (cumulative)": "{:,.2%}".format,
            }
        )
        summary.index.name = "component"
        return summary

    @property
    def F(self):
        """Return the row scores on each principal component."""
        return pd.DataFrame(
            np.diag(self.row_masses_**-0.5) @ self.svd_.U @ np.diag(self.svd_.s),
            index=self.row_masses_.index,
            columns=pd.RangeIndex(0, len(self.svd_.s)),
        )

    @property
    def G(self):
        """Return the column scores on each principal component."""
        return pd.DataFrame(
            np.diag(self.col_masses_**-0.5) @ self.svd_.V.T @ np.diag(self.svd_.s),
            index=self.col_masses_.index,
            columns=pd.RangeIndex(0, len(self.svd_.s)),
        )

    def row_coordinates(self, X):
        """The row principal coordinates."""

        _, row_names, _, _ = utils.make_labels_and_names(X)

        if isinstance(X, pd.DataFrame):
            try:
                X = X.sparse.to_coo().astype(float)
            except AttributeError:
                X = X.to_numpy()

        if self.copy:
            X = X.copy()

        # Normalise the rows so that they sum up to 1
        if isinstance(X, np.ndarray):
            X = X / X.sum(axis=1)[:, None]
        else:
            X = X / X.sum(axis=1)

        return pd.DataFrame(
            data=X @ sparse.diags(self.col_masses_.to_numpy() ** -0.5) @ self.svd_.V.T,
            index=row_names,
        )

    def column_coordinates(self, X):
        """The column principal coordinates."""

        _, _, _, col_names = util.make_labels_and_names(X)

        if isinstance(X, pd.DataFrame):
            is_sparse = X.dtypes.apply(pd.api.types.is_sparse).all()
            if is_sparse:
                X = X.sparse.to_coo()
            else:
                X = X.to_numpy()

        if self.copy:
            X = X.copy()

        # Transpose and make sure the rows sum up to 1
        if isinstance(X, np.ndarray):
            X = X.T / X.T.sum(axis=1)[:, None]
        else:
            X = X.T / X.T.sum(axis=1)

        return pd.DataFrame(
            data=X @ sparse.diags(self.row_masses_.to_numpy() ** -0.5) @ self.svd_.U,
            index=col_names,
        )

    def row_contributions(self):
        """Return the contributions of each row to the dimension's inertia.

        Contributions are returned as a score between 0 and 1 representing how much the row contributes to
        the dimension's inertia. The sum of contributions on each dimensions should sum to 1.
        It's usual to ignore score below 1/n_row.
        """
        F = self.F
        cont_r = (np.diag(self.row_masses_) @ (F**2)).div(self.svd_.s**2)
        return pd.DataFrame(cont_r.values, index=self.row_masses_.index)

    def column_contributions(self):
        """Return the contributions of each column to the dimension's inertia.

        Contributions are returned as a score between 0 and 1 representing how much the column contributes to
        the dimension's inertia. The sum of contributions on each dimensions should sum to 1.

        To obtain the contribution of a particular variable, you can sum the contribution of each of its levels.
        It's usual to ignore score below 1/n_column.
        """
        G = self.G
        cont_c = (np.diag(self.col_masses_) @ (G**2)).div(self.svd_.s**2)
        return pd.DataFrame(cont_c.values, index=self.col_masses_.index)

    def row_cos2(self):
        """Return the cos2 for each row against the dimensions.

        The cos2 value gives an indicator of the accuracy of the row projection on the dimension.

        Values above 0.5 usually means that the row is relatively accurately well projected onto that dimension. Its often
        used to identify which factor/dimension is important for a given element as the cos2 can be interpreted as the proportion
        of the variance of the element attributed to a particular factor.
        """
        F = self.F
        return (F**2).div(np.diag(F @ F.T) ** 2, axis=0)

    def column_cos2(self):
        """Return the cos2 for each column against the dimensions.

        The cos2 value gives an indicator of the accuracy of the column projection on the dimension.

        Values above 0.5 usually means that the column is relatively accurately well projected onto that dimension. Its often
        used to identify which factor/dimension is important for a given element as the cos2 can be interpreted as the proportion
        of the variance of the element attributed to a particular factor.
        """
        G = self.G
        return (G**2).div(np.diag(G @ G.T) ** 2, axis=0)

    def plot_coordinates(
        self,
        X,
        ax=None,
        figsize=(6, 6),
        x_component=0,
        y_component=1,
        show_row_labels=True,
        show_col_labels=True,
        **kwargs
    ):
        """Plot the principal coordinates."""

        if ax is None:
            fig, ax = plt.subplots(figsize=figsize)

        # Add style
        ax = plot.stylize_axis(ax)

        # Get labels and names
        row_label, row_names, col_label, col_names = util.make_labels_and_names(X)

        # Plot row principal coordinates
        row_coords = self.row_coordinates(X)
        ax.scatter(
            row_coords[x_component], row_coords[y_component], **kwargs, label=row_label
        )

        # Plot column principal coordinates
        col_coords = self.column_coordinates(X)
        ax.scatter(
            col_coords[x_component], col_coords[y_component], **kwargs, label=col_label
        )

        # Add row labels
        if show_row_labels:
            x = row_coords[x_component]
            y = row_coords[y_component]
            for xi, yi, label in zip(x, y, row_names):
                ax.annotate(label, (xi, yi))

        # Add column labels
        if show_col_labels:
            x = col_coords[x_component]
            y = col_coords[y_component]
            for xi, yi, label in zip(x, y, col_names):
                ax.annotate(label, (xi, yi))

        # Legend
        ax.legend()

        # Text
        ax.set_title("Principal coordinates")
        ei = self.explained_inertia_
        ax.set_xlabel(
            "Component {} ({:.2f}% inertia)".format(x_component, 100 * ei[x_component])
        )
        ax.set_ylabel(
            "Component {} ({:.2f}% inertia)".format(y_component, 100 * ei[y_component])
        )

        return ax
