class BackLinkMixin:
    back_link = None

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if callable(self.back_link):
            context["back_link"] = self.back_link(self)
        elif self.back_link:
            context["back_link"] = self.back_link
        return context


class TitleMixin:
    title = None

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.title:
            context["title"] = self.title
        return context